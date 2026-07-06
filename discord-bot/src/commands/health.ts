// /health — 라즈베리파이 상태 (CPU·메모리·온도·디스크) (docs/LOGGING.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder().setName("health").setDescription("라즈베리파이 상태 조회");

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
