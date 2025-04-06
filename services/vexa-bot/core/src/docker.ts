import { runBot } from "."
import { z } from 'zod';

// Define a schema that matches your JSON configuration
export const BotConfigSchema = z.object({
  platform: z.enum(["google", "zoom", "teams"]),
  meetingUrl: z.string().url(),
  botName: z.string(),
  token: z.string(),
  connectionId: z.string(),
  automaticLeave: z.object({
    waitingRoomTimeout: z.number().int(),
    noOneJoinedTimeout: z.number().int(),
    everyoneLeftTimeout: z.number().int()
  })
});


(function main() {
const rawConfig = process.env.BOT_CONFIG;
if (!rawConfig) {
  console.error("BOT_CONFIG environment variable is not set");
  process.exit(1);
}

  try {
  // Parse the JSON string from the environment variable
  const parsedConfig = JSON.parse(rawConfig);
  // Validate and parse the config using zod
  const botConfig = BotConfigSchema.parse(parsedConfig);

  // Run the bot with the validated configuration
  runBot(botConfig).catch((error) => {
    console.error("Error running bot:", error);
    process.exit(1);
  });
} catch (error) {
  console.error("Invalid BOT_CONFIG:", error);
  process.exit(1);
}
})()
