import React from "react";
import { Box, Text } from "ink";
import TextInput from "ink-text-input";
import { THEME } from "../theme.js";

interface CommandInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
}

export function CommandInput({ value, onChange, onSubmit, disabled = false }: CommandInputProps) {
  return (
    <Box
      marginX={1}
      paddingX={1}
      borderStyle="round"
      borderColor={disabled ? THEME.muted : THEME.brandAccent}
    >
      <Text color={disabled ? THEME.muted : THEME.brandAccent}>› </Text>
      <TextInput
        value={value}
        onChange={onChange}
        onSubmit={onSubmit}
        placeholder={disabled ? "Working..." : "message or /help"}
      />
    </Box>
  );
}
