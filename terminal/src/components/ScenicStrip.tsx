import React from "react";
import {Box, Text} from "ink";

type Segment = {
  text: string;
  color: string;
};

const BG = "#1f2637";
const SUN1 = "#f3a06f";
const SUN2 = "#d9774f";
const SUN3 = "#b95e3d";
const RING1 = "#ead36e";
const RING2 = "#c0ab52";
const SKY = "#37445f";
const FUJI_EDGE = "#213349";
const FUJI_DARK = "#4c6883";
const FUJI = "#7399be";
const FUJI_LIGHT = "#a8c7e4";
const SNOW = "#ffffff";
const SNOW2 = "#dff2ff";
const WAVE1 = "#a3eef2";
const WAVE2 = "#79cade";
const WAVE3 = "#4f7ea7";
const TREE1 = "#a0ec96";
const TREE2 = "#76ba70";
const TREE3 = "#4f7f52";
const TRUNK = "#7b5638";
const POT = "#d2ba69";

function seg(text: string, color = BG): Segment {
  return {text, color};
}

const ROWS: Segment[][] = [
  [
    seg("   ", BG),
    seg("▁▁", SKY),
    seg("                  ", BG),
    seg("▁▁", SKY),
    seg("                                                 ", BG),
  ],
  [
    seg("    ", BG),
    seg(" ▄▄▄ ", SUN1),
    seg("                ", BG),
    seg("  ▂▄▆▆▄▂", FUJI_EDGE),
    seg("                                     ", BG),
  ],
  [
    seg("   ", BG),
    seg("▄█████▄", SUN2),
    seg(" ", BG),
    seg("▁▁▁▁▁", RING2),
    seg("        ", BG),
    seg(" ▄████████▄ ", FUJI_DARK),
    seg("                       ", BG),
    seg("▂▄▂", TREE1),
    seg("    ", BG),
  ],
  [
    seg("  ", BG),
    seg("▐███████▌", SUN3),
    seg(" ", BG),
    seg("▔▔▔▔▔▔", RING1),
    seg("        ", BG),
    seg("▟██", FUJI_DARK),
    seg("▄", FUJI),
    seg("▄▄", FUJI_LIGHT),
    seg("▄▄", SNOW),
    seg("▄▄", FUJI_LIGHT),
    seg("▄", FUJI),
    seg("██▙", FUJI_DARK),
    seg("               ", BG),
    seg("▗▄██▄▖", TREE2),
    seg("    ", BG),
  ],
  [
    seg("  ", BG),
    seg(" ▀█████▀", SUN2),
    seg("        ", BG),
    seg("▟██", FUJI_EDGE),
    seg("██████", FUJI),
    seg("▀▀", SNOW2),
    seg("██████", FUJI),
    seg("██▙", FUJI_EDGE),
    seg("            ", BG),
    seg("▗██████▖", TREE1),
    seg("   ", BG),
  ],
  [
    seg(" ", BG),
    seg("≋", WAVE1),
    seg(" ≋", WAVE2),
    seg(" ≋", WAVE1),
    seg(" ≋", WAVE2),
    seg("    ", BG),
    seg("▐██", FUJI_EDGE),
    seg("█████", FUJI_DARK),
    seg(" ", BG),
    seg("█████", FUJI_DARK),
    seg("██▌", FUJI_EDGE),
    seg("        ", BG),
    seg("▐█", TRUNK),
    seg("▟██▙", TREE2),
    seg("      ", BG),
  ],
  [
    seg(" ", BG),
    seg("▂▃▄", WAVE2),
    seg("▂▃▄", WAVE1),
    seg("▂▃▄", WAVE2),
    seg("▂▃▄", WAVE1),
    seg("▂▃▄", WAVE2),
    seg("  ", BG),
    seg(" ▀███", FUJI_DARK),
    seg("▄", SNOW2),
    seg("▄", SNOW),
    seg("███▀ ", FUJI_DARK),
    seg("       ", BG),
    seg("▜████▛", TREE3),
    seg("    ", BG),
  ],
  [
    seg("▆▅▆▅", WAVE3),
    seg("▆▅▆▅", WAVE2),
    seg("▆▅▆▅", WAVE3),
    seg("▆▅▆▅", WAVE2),
    seg("▆▅▆▅", WAVE3),
    seg("▆▅▆▅", WAVE2),
    seg("▆▅▆▅", WAVE3),
    seg("▆▅▆▅", WAVE2),
    seg("▆▅▆▅", WAVE3),
    seg("▆▅▆▅", WAVE2),
    seg("▆▅▆▅", WAVE3),
    seg(" ", BG),
    seg("▔▔▔", POT),
    seg("   ", BG),
    seg("▆▅▆▅▆▅▆▅▆▅▆▅", WAVE3),
  ],
];

export function ScenicStrip(): React.ReactElement {
  if (process.env.NODE_ENV === "test" || !process.stdout.isTTY) {
    return <Box />;
  }
  return (
    <Box flexDirection="column" marginTop={1}>
      {ROWS.map((row, rowIndex) => (
        <Text key={`scenic-${rowIndex}`}>
          {row.map((segment, segmentIndex) => (
            <Text key={`scenic-${rowIndex}-${segmentIndex}`} color={segment.color}>
              {segment.text}
            </Text>
          ))}
        </Text>
      ))}
    </Box>
  );
}
