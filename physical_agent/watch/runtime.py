from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from physical_agent.config import DEFAULT_CONFIG_NAME, PhysicalAgentConfig, load_config
from physical_agent.drivers.loader import LoadedDriver, load_driver
from physical_agent.protocol.schemas import Action, ActionResult, Observation, RobotRuntimeProfile
from physical_agent.state import StateStore, open_state_store
from physical_agent.watch.safety import SafetyGate


ACTION_LEASE_SECONDS = 300
CLAIM_OWNER = "watch"


class WatchRuntime:
    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_NAME):
        self.config_path = Path(config_path).resolve()
        self.base_dir = self.config_path.parent
        self.config: PhysicalAgentConfig | None = None
        self.workspace: StateStore | None = None
        self.loaded_drivers: dict[str, LoadedDriver] = {}
        self.profiles: dict[str, RobotRuntimeProfile] = {}
        self._heartbeat_failure_counts: dict[str, int] = {}
        self._watchdog_halted_robots: set[str] = set()
        self.started = False

    async def setup(self) -> None:
        if self.started:
            return
        self.config = load_config(self.config_path)
        self.workspace = open_state_store(self.config, base_dir=self.base_dir)
        self.workspace.initialize()
        self.workspace.append_log("`physical-agent watch` started.", actor="watch")

        for robot_id, robot_config in self.config.robots.items():
            loaded = load_driver(
                robot_id=robot_id,
                driver_ref=robot_config.driver,
                config=robot_config.config,
                workspace_path=self.workspace.path,
                artifacts_path=self.workspace.artifacts_path,
                base_dir=self.base_dir,
            )
            await loaded.driver.connect()
            capabilities = loaded.driver.capabilities()
            self.loaded_drivers[robot_id] = loaded
            self._heartbeat_failure_counts[robot_id] = 0
            self._watchdog_halted_robots.discard(robot_id)
            self.profiles[robot_id] = RobotRuntimeProfile(
                robot_id=robot_id,
                kind=loaded.manifest.robot.kind,
                driver=loaded.manifest.name,
                status="connected",
                capabilities=capabilities,
                requires_approval=(
                    self.config.watch.require_human_approval
                    or not loaded.manifest.robot.supports_simulation
                ),
            )
            self.workspace.append_log(f"`{robot_id}` connected via `{loaded.manifest.name}`.", actor="watch")

        self.workspace.write_capabilities(self._capabilities_document())
        await self.update_world()
        self.started = True

    async def shutdown(self) -> None:
        await self._halt_loaded_drivers()
        for loaded in self.loaded_drivers.values():
            await loaded.driver.disconnect()
        if self.workspace is not None:
            self.workspace.append_log("`physical-agent watch` stopped.", actor="watch")
        self.started = False

    async def run_forever(self) -> None:
        await self.setup()
        assert self.config is not None
        try:
            while True:
                await self.step(setup=False)
                await asyncio.sleep(self.config.watch.tick_ms / 1000)
        finally:
            await self.shutdown()

    async def step(self, *, setup: bool = True) -> int:
        if setup:
            await self.setup()
        await self._heartbeat_loaded_drivers()
        workspace = self._workspace()
        workspace.recover_stale_actions(ACTION_LEASE_SECONDS)
        actions_doc = workspace.read_actions()
        safety_rules = workspace.read_safety()["rules"]
        executed_count = 0
        initial_pending_count = len(actions_doc["pending"])

        for _ in range(initial_pending_count):
            action = workspace.claim_next_ready_action(claim_owner=CLAIM_OWNER)
            if action is None:
                break
            latest_actions = workspace.read_actions()
            completed_ids = {item.id for item in latest_actions["completed"]}
            executed_ids = {
                item.id
                for item in latest_actions["completed"] + latest_actions["cancelled"]
            }
            for item in workspace.read_feedback().get("history", []):
                action_id = item.get("action_id")
                if action_id:
                    executed_ids.add(str(action_id))
            gate = SafetyGate(
                robots=self.profiles,
                safety_rules=safety_rules,
                completed_action_ids=completed_ids,
                executed_action_ids=executed_ids,
            )
            decision = gate.validate(action)
            if not decision.ok:
                result = ActionResult(status="failed", message=decision.message)
                workspace.mark_action_cancelled(action)
                await self._record_action_result(action, result)
                continue

            loaded = self.loaded_drivers[action.robot]
            try:
                result = await loaded.driver.execute(action)
            except Exception as exc:
                result = ActionResult(
                    status="failed",
                    message=f"Driver execute failed: {type(exc).__name__}: {exc}",
                    result={"error_type": type(exc).__name__},
                )
                workspace.mark_action_cancelled(action)
                executed_count += 1
                await self._record_action_result(action, result)
                continue
            if result.status == "completed":
                workspace.mark_action_completed(action)
            else:
                workspace.mark_action_cancelled(action)
            executed_count += 1
            await self._record_action_result(action, result)
            await self.update_world()

        if executed_count == 0:
            await self.update_world()
        return executed_count

    async def update_world(self) -> Observation:
        observations = [await loaded.driver.observe() for loaded in self.loaded_drivers.values()]
        merged = merge_observations(observations)
        self._workspace().write_world(merged)
        return merged

    def _capabilities_document(self) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for robot_id, profile in self.profiles.items():
            document[robot_id] = {
                "kind": profile.kind,
                "driver": profile.driver,
                "status": profile.status,
                "requires_approval": profile.requires_approval,
                "capabilities": [
                    capability.model_dump(mode="json", exclude_none=True)
                    for capability in profile.capabilities
                ],
            }
        return document

    async def _record_action_result(self, action: Action, result: ActionResult) -> None:
        workspace = self._workspace()
        feedback = workspace.read_feedback()
        latest = {
            "action_id": action.id,
            "status": result.status,
            "robot": action.robot,
            "capability": action.capability,
            "message": result.message,
            "result": result.result,
            "artifacts": result.artifacts,
        }
        history = list(feedback["history"])
        history.append(latest)
        workspace.write_feedback(latest, history)
        workspace.append_log(
            f"Action `{action.id}` {result.status}: {result.message}",
            actor="watch",
        )

    async def _heartbeat_loaded_drivers(self) -> None:
        if self.config is None or not self.config.watch.heartbeat_enabled:
            return
        for robot_id, loaded in self.loaded_drivers.items():
            try:
                await loaded.driver.heartbeat()
            except Exception as exc:
                failure_count = self._heartbeat_failure_counts.get(robot_id, 0) + 1
                self._heartbeat_failure_counts[robot_id] = failure_count
                self._record_driver_hook_failure(
                    robot_id,
                    "heartbeat",
                    exc,
                    extra_result={"failure_count": failure_count},
                )
                await self._maybe_halt_for_heartbeat_failure(
                    robot_id,
                    loaded,
                    failure_count,
                    exc,
                )
            else:
                previous_failure_count = self._heartbeat_failure_counts.get(robot_id, 0)
                self._heartbeat_failure_counts[robot_id] = 0
                self._watchdog_halted_robots.discard(robot_id)
                if previous_failure_count > 0:
                    self._record_heartbeat_recovered(robot_id, previous_failure_count)

    async def _halt_loaded_drivers(self) -> None:
        if self.config is None or not self.config.watch.halt_on_shutdown:
            return
        for robot_id, loaded in self.loaded_drivers.items():
            try:
                await loaded.driver.halt()
            except Exception as exc:
                self._record_driver_hook_failure(robot_id, "halt", exc)

    async def _maybe_halt_for_heartbeat_failure(
        self,
        robot_id: str,
        loaded: LoadedDriver,
        failure_count: int,
        heartbeat_exc: Exception,
    ) -> None:
        if self.config is None:
            return
        threshold = self.config.watch.heartbeat_failure_threshold
        if failure_count < threshold or robot_id in self._watchdog_halted_robots:
            return

        self._watchdog_halted_robots.add(robot_id)
        if not self.config.watch.halt_on_heartbeat_failure:
            self._record_watchdog_halt(
                robot_id=robot_id,
                failure_count=failure_count,
                threshold=threshold,
                halt_status="disabled",
                heartbeat_exc=heartbeat_exc,
            )
            return

        try:
            await loaded.driver.halt()
        except Exception as halt_exc:
            self._record_watchdog_halt(
                robot_id=robot_id,
                failure_count=failure_count,
                threshold=threshold,
                halt_status="failed",
                heartbeat_exc=heartbeat_exc,
                halt_exc=halt_exc,
            )
        else:
            self._record_watchdog_halt(
                robot_id=robot_id,
                failure_count=failure_count,
                threshold=threshold,
                halt_status="completed",
                heartbeat_exc=heartbeat_exc,
            )

    def _record_driver_hook_failure(
        self,
        robot_id: str,
        hook: str,
        exc: Exception,
        *,
        extra_result: dict[str, Any] | None = None,
    ) -> None:
        error_type = type(exc).__name__
        error_message = str(exc)
        message = (
            f"Driver {hook} failed for robot `{robot_id}`: "
            f"{error_type}: {error_message}"
        )
        result = {
            "hook": hook,
            "error_type": error_type,
            "error_message": error_message,
        }
        if extra_result is not None:
            result.update(extra_result)
        latest = {
            "status": "failed",
            "event": f"driver_{hook}",
            "robot": robot_id,
            "robot_id": robot_id,
            "message": message,
            "result": result,
            "artifacts": [],
        }
        self._record_driver_feedback(latest, message)

    def _record_heartbeat_recovered(
        self,
        robot_id: str,
        previous_failure_count: int,
    ) -> None:
        message = (
            f"Driver heartbeat recovered for robot `{robot_id}` "
            f"after {previous_failure_count} consecutive failure(s)."
        )
        latest = {
            "status": "completed",
            "event": "driver_heartbeat_recovered",
            "robot": robot_id,
            "robot_id": robot_id,
            "failure_count": previous_failure_count,
            "message": message,
            "result": {
                "hook": "heartbeat",
                "failure_count": previous_failure_count,
            },
            "artifacts": [],
        }
        self._record_driver_feedback(latest, message)

    def _record_watchdog_halt(
        self,
        *,
        robot_id: str,
        failure_count: int,
        threshold: int,
        halt_status: str,
        heartbeat_exc: Exception,
        halt_exc: Exception | None = None,
    ) -> None:
        heartbeat_error_type = type(heartbeat_exc).__name__
        heartbeat_error_message = str(heartbeat_exc)
        error_type = type(halt_exc).__name__ if halt_exc is not None else heartbeat_error_type
        error_message = str(halt_exc) if halt_exc is not None else heartbeat_error_message
        message = (
            f"Heartbeat watchdog threshold reached for robot `{robot_id}` "
            f"after {failure_count} consecutive failure(s); "
            f"threshold={threshold}; halt_status={halt_status}."
        )
        if halt_exc is not None:
            message = (
                f"{message} Halt failed: "
                f"{type(halt_exc).__name__}: {halt_exc}"
            )
        latest = {
            "status": "failed",
            "event": "driver_watchdog_halt",
            "robot": robot_id,
            "robot_id": robot_id,
            "failure_count": failure_count,
            "threshold": threshold,
            "halt_status": halt_status,
            "message": message,
            "result": {
                "hook": "halt",
                "failure_count": failure_count,
                "threshold": threshold,
                "halt_status": halt_status,
                "heartbeat_error_type": heartbeat_error_type,
                "heartbeat_error_message": heartbeat_error_message,
                "error_type": error_type,
                "error_message": error_message,
            },
            "artifacts": [],
        }
        self._record_driver_feedback(latest, message)

    def _record_driver_feedback(self, latest: dict[str, Any], message: str) -> None:
        workspace = self._workspace()
        feedback = workspace.read_feedback()
        history = list(feedback["history"])
        history.append(latest)
        workspace.write_feedback(latest, history)
        workspace.append_log(message, actor="watch")

    def _workspace(self) -> StateStore:
        if self.workspace is None:
            raise RuntimeError("WatchRuntime has not been set up.")
        return self.workspace


def merge_observations(observations: list[Observation]) -> Observation:
    if not observations:
        return Observation(summary="No robots are configured.")
    summary = " ".join(observation.summary for observation in observations if observation.summary)
    robots: dict[str, Any] = {}
    objects: dict[str, Any] = {}
    environment: dict[str, Any] = {}
    artifacts: list[str] = []
    raw: dict[str, Any] = {}
    for observation in observations:
        robots.update(observation.robots)
        objects.update(observation.objects)
        environment.update(observation.environment)
        artifacts.extend(observation.artifacts)
        raw.update(observation.raw)
    return Observation(
        summary=summary,
        robots=robots,
        objects=objects,
        environment=environment,
        artifacts=artifacts,
        raw=raw,
    )
