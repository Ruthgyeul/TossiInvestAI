// /cancel {orderId} — 미체결 주문 취소 (docs/DISCORD.md)
import { ChatInputCommandInteraction, SlashCommandBuilder } from "discord.js";

export const data = new SlashCommandBuilder()
  .setName("cancel")
  .setDescription("미체결 주문 취소")
  .addStringOption((opt) => opt.setName("orderid").setDescription("주문 ID").setRequired(true));

export async function execute(interaction: ChatInputCommandInteraction): Promise<void> {
  throw new Error("Not implemented");
}
