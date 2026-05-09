/**
 * Build the MessagePayload JSON pushed to the ARQ queue.
 * Shape is identical to the Telegram payload so Python workers need zero branching.
 */

import { WAMessage, isJidGroup, proto } from "baileys";
import { getChatName } from "./whitelist.js";

export interface MessagePayload {
  source_platform: "whatsapp";
  chat_id: string;
  chat_name: string;
  chat_type: "wa_group" | "wa_channel" | "personal";
  message_id: string;
  sender_id: string;
  sender_name: string;
  caption: string;
  image_data_b64: string;
  received_at: string; // ISO 8601 UTC
}

export function buildPayload(
  msg: WAMessage,
  imageCaption: string,
  imageDataB64: string
): MessagePayload {
  const jid = msg.key.remoteJid!;
  const msgId = msg.key.id!;

  const chatType: MessagePayload["chat_type"] = isJidGroup(jid)
    ? "wa_group"
    : jid.endsWith("@newsletter") || jid.endsWith("@broadcast")
      ? "wa_channel"
      : "personal";

  // sender_id: from participant (group/channel) or remoteJid (1-to-1)
  const rawSender = msg.key.participant ?? (jid.endsWith("@s.whatsapp.net") ? jid : null) ?? jid;
  // Strip multi-device suffix ":NN"
  const sender_id = rawSender.replace(/:\d+@/, "@");

  const ts = Number(msg.messageTimestamp ?? 0) * 1000;
  const received_at = new Date(ts || Date.now()).toISOString();

  return {
    source_platform: "whatsapp",
    chat_id: jid,
    chat_name: getChatName(jid),
    chat_type: chatType,
    message_id: msgId,
    sender_id,
    sender_name: msg.pushName ?? sender_id,
    caption: imageCaption,
    image_data_b64: imageDataB64,
    received_at,
  };
}
