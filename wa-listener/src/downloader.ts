/**
 * Media download — two-path strategy as per spec §5.3:
 * 1. Encrypted media (mediaKey present) → downloadMediaMessage
 * 2. Channel/newsletter or relayed messages without mediaKey → direct HTTP fetch
 * Then: validate magic bytes, resize to max 1024px, encode as base64.
 */

import { WAMessage, downloadMediaMessage, proto } from "baileys";
import sharp from "sharp";
import { log } from "./logger.js";

const MAX_SIDE = 1024;

export async function downloadAndEncode(
  msg: WAMessage,
  imageMsg: proto.Message.IImageMessage
): Promise<string | null> {
  let buffer: Buffer;

  try {
    if (imageMsg.mediaKey && imageMsg.mediaKey.length > 0) {
      // Encrypted media — normal group/personal message path
      buffer = (await downloadMediaMessage(msg, "buffer", {})) as Buffer;
    } else {
      // Channel/newsletter or relayed — fetch directly
      const directUrl =
        imageMsg.url ??
        (imageMsg.directPath
          ? `https://mmg.whatsapp.net${imageMsg.directPath}`
          : null);

      if (!directUrl) {
        log.warn({ msgId: msg.key?.id }, "no_media_url");
        return null;
      }

      const resp = await fetch(directUrl);
      if (!resp.ok) {
        log.warn({ status: resp.status, url: directUrl }, "media_fetch_failed");
        return null;
      }
      buffer = Buffer.from(await resp.arrayBuffer());
    }
  } catch (err) {
    log.error({ err, msgId: msg.key?.id }, "media_download_error");
    return null;
  }

  if (!isValidImage(buffer)) {
    log.warn({ msgId: msg.key?.id }, "invalid_image_magic_bytes");
    return null;
  }

  try {
    const resized = await sharp(buffer)
      .resize(MAX_SIDE, MAX_SIDE, { fit: "inside", withoutEnlargement: true })
      .jpeg({ quality: 85 })
      .toBuffer();
    return resized.toString("base64");
  } catch (err) {
    log.error({ err, msgId: msg.key?.id }, "image_resize_error");
    return null;
  }
}

function isValidImage(buf: Buffer): boolean {
  // JPEG: FF D8 FF
  if (buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return true;
  // PNG: 89 50 4E 47
  if (buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) return true;
  return false;
}
