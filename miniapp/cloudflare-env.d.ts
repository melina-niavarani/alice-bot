declare namespace Cloudflare {
  interface Env {
    DB?: D1Database;
    BOT_DB?: D1Database;
    BUCKET?: R2Bucket;
  }
}
