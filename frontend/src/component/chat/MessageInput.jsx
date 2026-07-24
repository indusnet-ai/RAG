import React, { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Mic, X, Square } from 'lucide-react';
import { speechToText } from '../../services/api';

const MessageInput = ({ onSend, disabled, onNewChat, onTriggerFileUpload, onStop, isStreaming }) => {
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState(null);
  const [audioChunks, setAudioChunks] = useState([]);
  const [audioLevels, setAudioLevels] = useState(Array(100).fill(0));
  const textareaRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const animationFrameRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }
  }, [input]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  const visualizeAudio = (stream) => {
    audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    analyserRef.current = audioContextRef.current.createAnalyser();
    const source = audioContextRef.current.createMediaStreamSource(stream);
    
    analyserRef.current.fftSize = 256;
    source.connect(analyserRef.current);
    
    const bufferLength = analyserRef.current.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    
    const updateLevels = () => {
      analyserRef.current.getByteFrequencyData(dataArray);
      
      // Calculate average volume
      const average = dataArray.reduce((a, b) => a + b) / bufferLength;
      
      // Normalize to 0-1 range and apply smoothing
      const normalizedLevel = Math.min(average / 128, 1);
      
      // Shift existing levels to the left and add new level at the end
      setAudioLevels(prev => {
        const newLevels = [...prev.slice(1), normalizedLevel];
        return newLevels;
      });
      
      animationFrameRef.current = requestAnimationFrame(updateLevels);
    };
    
    updateLevels();
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || disabled) return;

    onSend(input.trim());
    setInput('');
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      // Only submit if not currently listening (prevents mic trigger)
      if (!isListening) {
        handleSubmit(e);
      }
    }
  };
 
  const handleStopStreaming = () => {
    if (onStop) {
      onStop();
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks = [];

      recorder.ondataavailable = (event) => {
        chunks.push(event.data);
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(chunks, { type: 'audio/mp3' });
        try {
          const result = await speechToText(audioBlob);
          setInput(result.text);
        } catch (error) {
          console.error('Speech-to-text error:', error);
          alert('Failed to convert speech to text. Please try again.');
        }
        stream.getTracks().forEach(track => track.stop());
        
        // Clean up audio visualization
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
        if (audioContextRef.current) {
          audioContextRef.current.close();
        }
        setAudioLevels(Array(100).fill(0));
      };

      recorder.start();
      setMediaRecorder(recorder);
      setAudioChunks(chunks);
      setIsListening(true);
      
      // Start audio visualization
      visualizeAudio(stream);
    } catch (error) {
      console.error('Microphone access error:', error);
      alert('Microphone access denied. Please allow microphone access to use voice input.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
      setIsListening(false);
    }
  };

  const toggleSpeechRecognition = () => {
    if (isListening) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <div className="relative">
      {/* Gradient overlay for smooth blend */}
      <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-gray-50/95 via-gray-50/50 to-transparent pointer-events-none"></div>
      
      {/* Input container with neumorphic background */}
      <div className="relative bg-gradient-to-br from-gray-50 to-gray-100 pt-2 pb-6 px-4">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
          {/* Neumorphic input container */}
          <div className="relative bg-gradient-to-br from-gray-50 to-gray-100 rounded-3xl shadow-[8px_8px_16px_#b8b9be,-8px_-8px_16px_#ffffff] hover:shadow-[10px_10px_20px_#b8b9be,-10px_-10px_20px_#ffffff] transition-shadow duration-200">
            {/* Input wrapper */}
            <div className="flex items-end p-2">
              {/* Attach file button - neumorphic */}
              <button
                type="button"
                onClick={onTriggerFileUpload}
                disabled={disabled}
                className="flex-shrink-0 p-2 text-gray-500 hover:text-gray-700 rounded-lg transition self-end mb-1 ml-1 hover:bg-gradient-to-br hover:from-gray-100 hover:to-gray-200 hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff]"
                title="Attach file"
              >
                <Paperclip className="h-5 w-5" />
              </button> 

              {/* Text Input / Waveform Container */}
              <div className="flex-1 px-2 relative">
                {isListening ? (
                  /* Real-time Waveform visualization - neumorphic inset background */
                  <div className="flex items-center py-2 px-3 h-[36px] w-full overflow-hidden rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff]">
                    <div className="flex items-end gap-[3px] h-full w-full justify-end">
                      {audioLevels.map((level, i) => {
                        // Calculate height based on audio level (min 2px, max 28px)
                        const height = Math.max(2, level * 28);
                        return (
                          <div
                            key={i}
                            className="flex-shrink-0 bg-gradient-to-t from-blue-400 to-blue-600 rounded-full transition-all duration-75 shadow-sm"
                            style={{
                              width: '3px',
                              height: `${height}px`,
                            }}
                          />
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  /* Text Input when not listening */
                  <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="Message RAG Chatbot"
                    disabled={disabled}
                    rows={1}
                    className="w-full px-2 py-2 bg-transparent border-0 focus:outline-none resize-none disabled:opacity-50 disabled:cursor-not-allowed text-gray-800 placeholder-gray-500"
                    style={{ 
                      minHeight: '20px', 
                      maxHeight: '200px',
                      lineHeight: '20px'
                    }}
                  />
                )}
              </div>

              {/* Microphone Button - neumorphic */}
              <button
                type="button"
                onClick={toggleSpeechRecognition}
                disabled={disabled || isStreaming}
                className={`flex-shrink-0 p-2 rounded-lg transition-all duration-200 self-end mb-1 ${
                  isListening 
                    ? 'bg-gradient-to-br from-gray-50 to-gray-100 text-gray-700 shadow-[inset_3px_3px_6px_#b8b9be,inset_-3px_-3px_6px_#ffffff]' 
                    : 'text-gray-500 hover:text-gray-700 bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff]'
                } ${disabled || isStreaming ? 'cursor-not-allowed opacity-50' : ''}`}
                title={isListening ? "Stop listening" : "Start voice input"}
              >
                {isListening ? (
                  <X className="h-5 w-5" />
                ) : (
                  <Mic className="h-5 w-5" />
                )}
              </button>

              {/* Action Buttons - Show either Stop or Send button */}
              {isStreaming ? (
                /* Stop Button - shown when streaming */
                <button
                  type="button"
                  onClick={handleStopStreaming}
                  className="flex-shrink-0 p-2 rounded-lg transition-all duration-200 self-end mb-1 mr-1 ml-2 bg-gradient-to-br  shadow-[inset_1px_1px_4px_#b8b9be,inset_-1px_-1px_4px_#ffffff]"
                  title="Stop generating response"
                >
                  <Square fill="black" stroke="black"  className="h-5 w-5" />
                </button>
              ) : (
                /* Send Button - shown when not streaming */
                <button
                  type="submit"
                  disabled={disabled || !input.trim()}
                  className={`flex-shrink-0 p-2 rounded-lg transition-all duration-200 self-end mb-1 mr-1 ml-2 ${
                    input.trim() && !disabled
                      ? 'bg-gradient-to-br from-gray-50 to-gray-100 text-gray-700 shadow-[inset_3px_3px_6px_#b8b9be,inset_-3px_-3px_6px_#ffffff]'
                      : 'text-gray-500 hover:text-gray-700 bg-gradient-to-br from-gray-50 to-gray-100 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff]'
                  }`}
                >
                  <Send className="h-5 w-5" />
                </button>
              )}
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};

export default MessageInput;