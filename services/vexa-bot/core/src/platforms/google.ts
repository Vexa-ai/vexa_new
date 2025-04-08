import { Page } from 'playwright';
import { log, randomDelay } from '../utils';
import { BotConfig } from '../types';

export async function handleGoogleMeet(botConfig: BotConfig, page: Page): Promise<void> {
  const leaveButton = `//button[@aria-label="Leave call"]`;

  log('Joining Google Meet');
  try {
    await joinMeeting(page, botConfig.meetingUrl, botConfig.botName)
  } catch (error: any) {
    console.error(error.message)
    return
  }

  // Setup websocket connection and meeting admission concurrently
  log("Starting WebSocket connection while waiting for meeting admission");
  try {
    // Run both processes concurrently
    const [isAdmitted] = await Promise.all([
      // Wait for admission to the meeting
      waitForMeetingAdmission(page, leaveButton, botConfig.automaticLeave?.waitingRoomTimeout ?? 300000)
        .catch(error => {
          log("Meeting admission failed: " + error.message);
          return false;
        }),
      
      // Prepare for recording (expose functions, etc.) while waiting for admission
      prepareForRecording(page)
    ]);

    if (!isAdmitted) {
      console.error("Bot was not admitted into the meeting");
      return;
    }

    log("Successfully admitted to the meeting, starting recording");
    // Pass meeting_id to startRecording
    await startRecording(page, botConfig.meeting_id, botConfig.meetingUrl, botConfig.botName);
  } catch (error: any) {
    console.error(error.message)
    return
  }
}

// New function to wait for meeting admission
const waitForMeetingAdmission = async (page: Page, leaveButton: string, timeout: number): Promise<boolean> => {
  try {
    await page.waitForSelector(leaveButton, { timeout });
    log("Successfully admitted to the meeting");
    return true;
  } catch {
    throw new Error("Bot was not admitted into the meeting within the timeout period");
  }
};

// Prepare for recording by exposing necessary functions
const prepareForRecording = async (page: Page): Promise<void> => {
  // Expose the logBot function to the browser context
  await page.exposeFunction('logBot', (msg: string) => {
    log(msg);
  });
};

const joinMeeting = async (page: Page, meetingUrl: string, botName: string) => {
  const enterNameField = 'input[type="text"][aria-label="Your name"]';
  const joinButton = '//button[.//span[text()="Ask to join"]]';
  const muteButton = '[aria-label*="Turn off microphone"]';
  const cameraOffButton = '[aria-label*="Turn off camera"]';

  await page.goto(meetingUrl, { waitUntil: "networkidle" });
  await page.bringToFront();

  // Add a longer, fixed wait after navigation for page elements to settle
  log("Waiting for page elements to settle after navigation...");
  await page.waitForTimeout(5000); // Wait 5 seconds

  // Enter name and join
  // Keep the random delay before interacting, but ensure page is settled first
  await page.waitForTimeout(randomDelay(1000)); 
  log("Attempting to find name input field...");
  // Increase timeout drastically
  await page.waitForSelector(enterNameField, { timeout: 120000 }); // 120 seconds
  log("Name input field found.");

  await page.waitForTimeout(randomDelay(1000));
  await page.fill(enterNameField, botName);

  // Mute mic and camera if available
  try {
    await page.waitForTimeout(randomDelay(500));
    await page.click(muteButton, { timeout: 200 });
    await page.waitForTimeout(200);
  } catch (e) {
    log("Microphone already muted or not found.");
  }
  try {
    await page.waitForTimeout(randomDelay(500));
    await page.click(cameraOffButton, { timeout: 200 });
    await page.waitForTimeout(200);
  } catch (e) {
    log("Camera already off or not found.");
  }

  await page.waitForSelector(joinButton, { timeout: 60000 });
  await page.click(joinButton);
  log(`${botName} joined the Meeting.`);
}

// Modified to accept meeting_id and all required WhisperLive parameters
const startRecording = async (page: Page, meetingId: number, meetingUrl: string, botName: string) => {
  log(`Starting actual recording with WebSocket connection for meeting ${meetingId}`);
  
  // Pass all required parameters to the evaluated function
  await page.evaluate(async ({ meetingId, meetingUrl, botName }) => {
    // Define options directly here or receive them if needed
    const option = {
      language: null, // Set to null to trigger language inference/auto-detection
      task: "transcribe", // Default or configurable?
      modelSize: "small", // Default or configurable?
      useVad: false, // Disable VAD for testing
    }

    let socket: WebSocket | null = null; // Declare socket here
    let audioContext: AudioContext | null = null; // Declare audioContext here
    let processor: ScriptProcessorNode | null = null; // Declare processor here
    let source: MediaStreamAudioSourceNode | null = null; // Declare source here

    await new Promise<void>((resolve, reject) => {
      try {
        (window as any).logBot("Starting recording process.");
        const mediaElements = Array.from(document.querySelectorAll("audio, video")).filter(
          (el: any) => !el.paused
        );
        if (mediaElements.length === 0) {
          return reject(new Error("[BOT Error] No active media elements found."));
        }
        const element: any = mediaElements[0];

        const stream = element.srcObject || element.captureStream();
        if (!(stream instanceof MediaStream)) {
          return reject(new Error("[BOT Error] Unable to obtain a MediaStream."));
        }

        // WebSocket connection
        const wsUrl = (window as any).WHISPER_LIVE_URL || "ws://whisperlive:9090";
        (window as any).logBot(`Attempting to connect WebSocket to: ${wsUrl} for meeting ${meetingId}`);
        
        let isServerReady = false;
        let language = option.language;
        let retryCount = 0;
        const maxRetries = 5;
        const retryDelay = 2000;
        
        const cleanup = () => {
            (window as any).logBot("Cleaning up audio processing and WebSocket.");
            if (processor) processor.disconnect();
            if (source) source.disconnect();
            if (audioContext && audioContext.state !== 'closed') audioContext.close();
            if (socket && socket.readyState === WebSocket.OPEN) socket.close();
            socket = null;
            audioContext = null;
            processor = null;
            source = null;
            resolve(); // Resolve the promise
        };
        
        const setupWebSocket = () => {
          try {
            if (socket) { try { socket.close(); } catch (err) {} }
            
            socket = new WebSocket(wsUrl);
            
            socket.onopen = function() {
              (window as any).logBot("WebSocket connection opened.");
              retryCount = 0;
              
              // Create a unique identifier for this connection
              const uid = `bot-${meetingId}-${Date.now()}`;
              
              if (socket) {
                // Send the initial configuration with ALL required parameters
                socket?.send(
                  JSON.stringify({
                    uid: uid, // Required by WhisperLive
                    platform: "google_meet", // Required by WhisperLive
                    meeting_url: meetingUrl, // Required by WhisperLive
                    token: `bot-token-${meetingId}`, // Required by WhisperLive
                    meeting_id: meetingId,
                    language: option.language,
                    task: option.task,
                    model: option.modelSize,
                    use_vad: option.useVad
                  })
                );
                
                (window as any).logBot("Sent configuration to WhisperLive server with all required parameters");
              }
            };

            socket.onmessage = (event) => {
              (window as any).logBot("Received message: " + event.data);
              const data = JSON.parse(event.data);
              // **MODIFIED**: Check for meeting_id if server includes it in responses
              // if (data["meeting_id"] !== meetingId) return; 

              if (data["status"] === "WAIT") {
                (window as any).logBot(`Server busy: ${data["message"]}`);
              } else if (!isServerReady && data["message"] === "SERVER_READY") {
                isServerReady = true;
                (window as any).logBot("Server is ready. Starting audio processing.");
                startAudioProcessing(stream);
              } else if (language === null && data["language"]) {
                (window as any).logBot(`Language detected: ${data["language"]}`);
              } else if (data["message"] === "DISCONNECT") {
                (window as any).logBot("Server requested disconnect.");
                if (socket) { socket.close(); }
              } else {
                // Enhanced logging for transcription data
                if (data["text"] && data["text"].trim() !== "") {
                  (window as any).logBot(`TRANSCRIPT: [${new Date().toISOString()}] Text: "${data["text"]}" Confidence: ${data["confidence"] || "N/A"}`);
                  
                  // Additional details if available
                  if (data["start_time"] && data["end_time"]) {
                    (window as any).logBot(`TRANSCRIPT_TIMING: Start: ${data["start_time"]}s, End: ${data["end_time"]}s, Duration: ${(data["end_time"] - data["start_time"]).toFixed(2)}s`);
                  }
                  
                  // Log the complete data for debugging
                  (window as any).logBot(`TRANSCRIPT_FULL_DATA: ${JSON.stringify(data)}`);
                } else if (data["text"] !== undefined) {
                  // Log empty transcripts to help with debugging
                  (window as any).logBot(`TRANSCRIPT_EMPTY: Server returned empty transcription text`);
                } else {
                  // Log other messages that aren't SERVER_READY, WAIT, etc.
                  (window as any).logBot(`UNKNOWN_MESSAGE: ${JSON.stringify(data)}`);
                }
              }
            };

            socket.onerror = (event) => {
              (window as any).logBot(`WebSocket error: ${JSON.stringify(event)}`);
              // Consider calling cleanup() or attempting reconnect based on error type
            };

            socket.onclose = (event) => {
              (window as any).logBot(`WebSocket closed. Code: ${event.code}, Reason: ${event.reason}`);
              cleanup(); // Clean up resources on close
              // Remove automatic retry logic here if cleanup handles resolution/rejection
            };
          } catch (e: any) {
            (window as any).logBot(`Error setting up WebSocket: ${e.message}`);
             cleanup(); // Clean up on initial setup error
             reject(new Error(`WebSocket setup failed: ${e.message}`)); // Reject the main promise
          }
        };

        const startAudioProcessing = (mediaStream: MediaStream) => {
             try {
                  if (audioContext && audioContext.state !== 'closed') {
                       (window as any).logBot("Audio context already exists or is closing.");
                       return;
                  }
                  audioContext = new AudioContext();
                  source = audioContext.createMediaStreamSource(mediaStream);
                  processor = audioContext.createScriptProcessor(4096, 1, 1);

                  // The expected sample rate for WhisperLive
                  const TARGET_SAMPLE_RATE = 16000;
                  const currentSampleRate = audioContext.sampleRate;
                  (window as any).logBot(`Current audio context sample rate: ${currentSampleRate}Hz, target rate: ${TARGET_SAMPLE_RATE}Hz`);

                  processor.onaudioprocess = (e) => {
                      if (!socket || socket.readyState !== WebSocket.OPEN || !isServerReady || !audioContext) return;
                      const inputData = e.inputBuffer.getChannelData(0);
                      
                      // --- DEBUG: Log raw audio amplitude ---
                      let maxAbsValue = 0;
                      let sumAbsValue = 0;
                      for (let i = 0; i < inputData.length; i++) {
                          const absValue = Math.abs(inputData[i]);
                          if (absValue > maxAbsValue) {
                              maxAbsValue = absValue;
                          }
                          sumAbsValue += absValue;
                      }
                      const avgAbsValue = sumAbsValue / inputData.length;
                      (window as any).logBot(`RAW_AUDIO_CHUNK: Length=${inputData.length}, AvgAbs=${avgAbsValue.toFixed(4)}, MaxAbs=${maxAbsValue.toFixed(4)}`);
                      // --- END DEBUG ---
                      
                      try {
                          if (socket && socket.readyState === WebSocket.OPEN) {
                              // Step 1: Create a copy of the input data
                              const data = new Float32Array(inputData);
                              
                              // Step 2: Perform resampling to 16kHz if needed
                              let audioToSend;
                              
                              if (currentSampleRate !== TARGET_SAMPLE_RATE) {
                                  // Calculate target length based on the ratio of sample rates
                                  const targetLength = Math.round(data.length * (TARGET_SAMPLE_RATE / currentSampleRate));
                                  const resampledData = new Float32Array(targetLength);
                                  
                                  // Linear interpolation resampling
                                  const springFactor = (data.length - 1) / (targetLength - 1);
                                  resampledData[0] = data[0]; // First sample stays the same
                                  resampledData[targetLength - 1] = data[data.length - 1]; // Last sample stays the same
                                  
                                  // Interpolate all samples in between
                                  for (let i = 1; i < targetLength - 1; i++) {
                                      const index = i * springFactor;
                                      const leftIndex = Math.floor(index);
                                      const rightIndex = Math.ceil(index);
                                      const fraction = index - leftIndex;
                                      resampledData[i] = data[leftIndex] + (data[rightIndex] - data[leftIndex]) * fraction;
                                  }
                                  
                                  audioToSend = resampledData;
                                  (window as any).logBot(`Resampled audio: ${data.length} samples at ${currentSampleRate}Hz → ${resampledData.length} samples at ${TARGET_SAMPLE_RATE}Hz`);
                              } else {
                                  audioToSend = data;
                                  (window as any).logBot(`Audio already at target rate: ${TARGET_SAMPLE_RATE}Hz`);
                              }

                              // Step 3: Convert Float32Array to Int16Array as expected by WhisperLive
                              const int16Data = new Int16Array(audioToSend.length);
                              for (let i = 0; i < audioToSend.length; i++) {
                                  // Ensure values are in the valid range [-1, 1] then scale to Int16 range
                                  const sample = Math.max(-1, Math.min(1, audioToSend[i]));
                                  int16Data[i] = sample < 0 ? sample * 32768 : sample * 32767;
                              }

                              // Step 4: Send the processed audio data
                              socket.send(int16Data.buffer);
                          } else {
                              (window as any).logBot("WebSocket not ready or closed, skipping audio send.");
                          }
                      } catch (error) {
                          (window as any).logBot(`Error sending audio data: ${error}`);
                      }
                  };

                  source.connect(processor);
                  processor.connect(audioContext.destination); // Connect to destination to start processing
             } catch (audioError: any) {
                  (window as any).logBot(`Error starting audio processing: ${audioError.message}`);
                  cleanup(); // Cleanup if audio setup fails
                  reject(audioError); // Reject the main promise
             }
        };

        // Initial WebSocket setup call
        setupWebSocket();

      } catch (e: any) {
        (window as any).logBot(`Error in evaluated function scope: ${e.message}`);
        reject(e);
      }
    });

  }, { meetingId, meetingUrl, botName }); // Pass meetingId, meetingUrl, and botName to the evaluation context
};

// Remove recordMeeting function if redundant
// const recordMeeting = async (page: Page, meetingUrl: string, token: string, connectionId: string, platform: string) => {
//   ...
// };
