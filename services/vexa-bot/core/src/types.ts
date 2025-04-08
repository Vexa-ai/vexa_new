export type BotConfig = {
  meeting_id: number;
  platform: "google" | "zoom" | "teams",
  meetingUrl: string,
  botName: string,
  automaticLeave?: {
    waitingRoomTimeout?: number,
    noOneJoinedTimeout?: number,
    everyoneLeftTimeout?: number
  }
}
