import React from "react";
import { Box, Text } from "ink";
import { THEME } from "../theme.js";

export const FULL_BANNER_MIN_COLUMNS = 58;

export const FULL_MOCE_LOGO = [
  "███╗   ███╗  ██████╗   ██████╗ ███████╗",
  "████╗ ████║ ██╔═══██╗ ██╔════╝ ██╔════╝",
  "██╔████╔██║ ██║   ██║ ██║      █████╗",
  "██║╚██╔╝██║ ██║   ██║ ██║      ██╔══╝",
  "██║ ╚═╝ ██║ ╚██████╔╝ ╚██████╗ ███████╗",
  "╚═╝     ╚═╝  ╚═════╝   ╚═════╝ ╚══════╝"
] as const;

export function selectBannerVariant(columns?: number): "full" | "compact" {
  return Number.isFinite(columns) && (columns ?? 0) >= FULL_BANNER_MIN_COLUMNS
    ? "full"
    : "compact";
}

export function BrandBanner({ columns }: { columns?: number }) {
  const variant = selectBannerVariant(columns);
  return (
    <Box flexDirection="column" paddingX={1} marginBottom={1}>
      {variant === "full"
        ? FULL_MOCE_LOGO.map((line) => (
            <Text key={line} color={THEME.brandLogo} bold>{line}</Text>
          ))
        : <Text color={THEME.brandAccent} bold>MOCE · PHYSICAL AGENT</Text>}
      {variant === "full" ? (
        <Text color={THEME.brandAccent} bold>PHYSICAL AGENT · SAFE CONTROL PLANE</Text>
      ) : null}
      <Text color={THEME.muted}>type /help to explore</Text>
    </Box>
  );
}
