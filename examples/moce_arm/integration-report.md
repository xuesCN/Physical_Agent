# Integration Report

Source: `https://github.com/wanhaoniu/MomoAgent`

## Evidence

- MCP bridge
- serial transport
- HTTP API
- voice features
- light control
- movement
- manipulation

## Scanned Files

- README_ZH.md
- HF_README_DRAFT.md
- .gitignore
- README.md
- LICENSE
- step/Base_motor_holder_SO101.STEP
- step/manual_joint_wrench_soarm_moce.STEP
- step/Wrist_Roll_Follower_SO101.STEP
- step/forearm_soarm_moce.STEP
- step/ee_3jaw_cross_assembly_soarm_moce.STEP
- step/desktop_mount_base_soarm_moce.STEP
- step/Soarm_Moce_Assembly.STEP
- step/moving_jaw_so101.STEP
- step/desktop_mount_screw_3dprint_soarm_moce.STEP
- step/Wrist_Roll_Pitch_SO101.STEP
- step/servo_soarm_moce.STEP
- step/ee_2jaw_linear_assembly_soarm_moce.STEP
- step/reducer_assembly_j3_soarm_moce.STEP
- step/base_so101.STEP
- step/reducer_assembly_j2_soarm_moce.STEP

## Capabilities

- observe: Observe the current device or bridge state.
- home: Return the arm to its configured home pose.
- stop: Stop arm motion and hold the current pose.
- move_joint: Move one available joint to an absolute target or by a relative delta.
- move_joints: Move several available joints to target angles.
- set_gripper: Set the gripper opening ratio.
- open_gripper: Fully open the gripper.
- close_gripper: Fully close the gripper.

## Next Steps

- Keep the driver logic on the watch side.
- Wire the endpoint, token, and timeout settings into physical_driver.yaml.
- Move hardware SDK calls into driver.py.
- Run mock mode first, then switch to the real bridge or device.
- Add a focused pytest for each capability you keep.
- Verify observation and stop behavior before enabling motion or gripper commands.
- If the repo already has an integration script, copy the transport logic, not the README wording.
