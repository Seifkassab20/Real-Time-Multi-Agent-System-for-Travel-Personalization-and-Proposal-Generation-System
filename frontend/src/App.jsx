import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  User,
  Calendar,
  DollarSign,
  MapPin,
  Heart,
  AlertCircle,
  MoreHorizontal,
  Phone,
  WifiOff,
  Mic,
  RefreshCw,
  MessageCircleQuestion,
  Hotel,
  Sparkles,
  Coffee
} from 'lucide-react';

const WEBSOCKET_URL = 'ws://localhost:8000/ws/stream';
const API_BASE_URL = 'http://localhost:8000';

const TravelDashboard = () => {
  const [isCallActive, setIsCallActive] = useState(false);
  const [clientName, setClientName] = useState("");
  const [clientNumber, setClientNumber] = useState("");
  const [callDuration, setCallDuration] = useState(0);
  const [transcripts, setTranscripts] = useState([]);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [profileQuestions, setProfileQuestions] = useState([]);
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [questionsError, setQuestionsError] = useState(null);
  const [recommendations, setRecommendations] = useState(null);
  const currentCallIdRef = useRef(null);

  const mediaStreamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const websocketRef = useRef(null);
  const audioChunksRef = useRef([]);

  // Timer logic for live call
  useEffect(() => {
    let interval;
    if (isCallActive) {
      interval = setInterval(() => {
        setCallDuration(prev => prev + 1);
      }, 1000);
    } else {
      setCallDuration(0);
    }
    return () => clearInterval(interval);
  }, [isCallActive]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (websocketRef.current) {
        websocketRef.current.close();
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const fetchProfileQuestions = useCallback(async (callId) => {
    if (!callId) {
      console.log('No call_id available to fetch questions');
      return;
    }

    setQuestionsLoading(true);
    setQuestionsError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/profile/questions/${callId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Profile questions received:', data);

      if (data.success && data.questions) {
        // Replace old questions with new ones
        setProfileQuestions(data.questions);
      } else if (data.error) {
        setQuestionsError(data.error);
        setProfileQuestions([]);
      } else {
        setProfileQuestions([]);
      }
    } catch (error) {
      console.error('Error fetching profile questions:', error);
      setQuestionsError(error.message);
      setProfileQuestions([]);
    } finally {
      setQuestionsLoading(false);
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(WEBSOCKET_URL);

      ws.onopen = () => {
        console.log('WebSocket connected');
        setConnectionStatus('connected');
        resolve(ws);
      };

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        console.log('Received:', message);

        if (message.type === 'call_started') {
          // Store the call_id when call starts
          currentCallIdRef.current = message.call_id;
          console.log('Call started with ID:', message.call_id);
        } else if (message.type === 'transcript') {
          setTranscripts(prev => [...prev, {
            text: message.text,
            segment: message.segment,
            timestamp: new Date().toLocaleTimeString()
          }]);
        } else if (message.type === 'extraction_done') {
          // Extraction completed - fetch updated profile questions
          console.log('Extraction done for segment:', message.segment);
          if (message.call_id) {
            fetchProfileQuestions(message.call_id);
          } else if (currentCallIdRef.current) {
            fetchProfileQuestions(currentCallIdRef.current);
          }
        } else if (message.type === 'profile_update') {
          console.log('Profile updated:', message.profile);
        } else if (message.type === 'recommendations') {
          console.log('Recommendations received:', message);
          setRecommendations({
            hotel: message.hotel,
            itinerary: message.itinerary,
            budget_breakdown: message.budget_breakdown,
            lastUpdated: new Date().toLocaleTimeString(),
            segment: message.segment
          });
        } else if (message.type === 'recommendation') {
          console.log('Recommendation:', message.data);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionStatus('error');
        reject(error);
      };

      ws.onclose = () => {
        console.log('WebSocket closed');
        setConnectionStatus('disconnected');
      };

      websocketRef.current = ws;
    });
  }, [fetchProfileQuestions]);

  const startAudioStreaming = useCallback((stream) => {
    let segmentChunks = [];
    const SEGMENT_DURATION_MS = 10000; // 10 seconds per segment

    const createAndStartRecorder = () => {
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          segmentChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Combine all chunks into a single blob with valid headers
        if (segmentChunks.length > 0 && websocketRef.current?.readyState === WebSocket.OPEN) {
          const completeBlob = new Blob(segmentChunks, { type: 'audio/webm;codecs=opus' });
          segmentChunks = []; // Clear for next segment

          // Convert to base64 and send
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64Audio = reader.result.split(',')[1];
            websocketRef.current.send(JSON.stringify({
              type: 'audio_segment',
              data: base64Audio,
              mimeType: 'audio/webm;codecs=opus',
              duration: SEGMENT_DURATION_MS / 1000
            }));
            console.log('Sent 20-second audio segment');
          };
          reader.readAsDataURL(completeBlob);

          // Store for potential download
          audioChunksRef.current.push(completeBlob);
        }

        // Start a new recording if still active
        if (stream.active && websocketRef.current?.readyState === WebSocket.OPEN) {
          createAndStartRecorder();
        }
      };

      // Collect data frequently for smooth accumulation
      mediaRecorder.start(1000);
      console.log('Audio segment recording started');

      // Stop after 20 seconds to create a complete segment
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
      }, SEGMENT_DURATION_MS);
    };

    // Start the first recording
    createAndStartRecorder();
    console.log('Audio streaming started (20-second segments)');
  }, []);

  const handleToggleCall = async () => {
    if (isCallActive) {
      // End the call
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach(track => track.stop());
        mediaStreamRef.current = null;
      }
      if (websocketRef.current) {
        websocketRef.current.send(JSON.stringify({ type: 'stop' }));
        websocketRef.current.close();
        websocketRef.current = null;
      }
      setIsCallActive(false);
      setConnectionStatus('disconnected');
      console.log("Call Ended");
    } else {
      // Start the call
      if (!clientName.trim()) {
        alert("Please enter a client name first.");
        return;
      }

      try {
        console.log(`Starting call with ${clientName} (${clientNumber})...`);

        // Connect to WebSocket first
        const ws = await connectWebSocket();

        // Send client info
        ws.send(JSON.stringify({
          type: 'start_call',
          clientName: clientName,
          clientPhone: clientNumber
        }));

        // Request microphone access
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            sampleRate: 16000,
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true
          }
        });
        mediaStreamRef.current = stream;

        // Start streaming audio
        startAudioStreaming(stream);

        setIsCallActive(true);
        setTranscripts([]); // Clear previous transcripts
      } catch (err) {
        console.error("Error starting call:", err);
        alert("Could not start call. Please check your microphone permissions and ensure the backend is running.");
        if (websocketRef.current) {
          websocketRef.current.close();
        }
      }
    }
  };

  return (
    <div className="min-h-screen bg-[#F0F6FF] p-4 md:p-8 font-sans text-slate-800">

      {/* --- Top Header --- */}
      <header className="flex flex-col md:flex-row md:items-center justify-between bg-white p-4 rounded-xl shadow-sm mb-6 border border-slate-100 gap-4">

        <div className="flex flex-col md:flex-row items-start md:items-center gap-4 w-full md:w-auto">

          {/* Status Indicator (Live / Offline) */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border transition-colors duration-300 ${isCallActive
            ? 'bg-red-50 border-red-100 text-red-700'
            : 'bg-slate-100 border-slate-200 text-slate-500'
            }`}>
            {isCallActive ? (
              <>
                <div className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500"></span>
                </div>
                <span className="font-bold text-sm whitespace-nowrap">Live {formatTime(callDuration)}</span>
              </>
            ) : (
              <>
                <WifiOff size={14} />
                <span className="font-bold text-sm text-slate-600">Offline</span>
              </>
            )}
          </div>

          <div className="h-8 w-px bg-slate-200 hidden md:block"></div>

          {/* Client Inputs */}
          <div className="flex flex-col sm:flex-row gap-3 w-full md:w-auto">
            {/* Name Input */}
            <div className="relative group w-full sm:w-auto">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <User size={16} className="text-gray-400 group-focus-within:text-blue-500 transition-colors" />
              </div>
              <input
                type="text"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                placeholder="Client Name"
                className="block w-full sm:w-48 pl-10 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-semibold text-slate-700 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:bg-white transition-all"
                disabled={isCallActive}
              />
            </div>

            {/* Number Input */}
            <div className="relative group w-full sm:w-auto">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Phone size={16} className="text-gray-400 group-focus-within:text-blue-500 transition-colors" />
              </div>
              <input
                type="tel"
                value={clientNumber}
                onChange={(e) => setClientNumber(e.target.value)}
                placeholder="Phone Number"
                className="block w-full sm:w-40 pl-10 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:bg-white transition-all"
                disabled={isCallActive}
              />
            </div>
          </div>
        </div>

        {/* Action Button */}
        <div className="flex gap-3 w-full md:w-auto">
          <button
            onClick={handleToggleCall}
            className={`${isCallActive ? 'bg-red-500 hover:bg-red-600 shadow-red-200' : 'bg-blue-600 hover:bg-blue-700 shadow-blue-200'} w-full md:w-auto text-white px-6 py-2 rounded-lg font-medium transition shadow-sm flex items-center justify-center gap-2 min-w-[140px]`}
          >
            <Phone size={16} className={isCallActive ? "animate-pulse" : ""} />
            {isCallActive ? "End Call" : "Start Call"}
          </button>
        </div>
      </header>

      {/* --- Main Grid Layout --- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left Column (Span 2) */}
        <div className="lg:col-span-2 flex flex-col gap-6">

          {/* 1. Customer Profile Card */}
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
            <div className="flex justify-between items-start mb-6">
              <h2 className="text-xl font-bold text-slate-800">Customer Profile</h2>
              <span className="bg-green-100 text-green-700 text-xs font-bold px-3 py-1.5 rounded-full">
                85% Complete
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-y-8 gap-x-8">
              {/* Travelers */}
              <div className="flex gap-4">
                <div className="bg-blue-50 p-2.5 rounded-lg h-fit">
                  <User className="text-blue-600 w-5 h-5" />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">Travelers</p>
                  <p className="font-semibold text-slate-800">2 Adults (30s)</p>
                </div>
              </div>

              {/* Dates */}
              <div className="flex gap-4">
                <div className="bg-blue-50 p-2.5 rounded-lg h-fit">
                  <Calendar className="text-blue-600 w-5 h-5" />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">Dates</p>
                  <p className="font-semibold text-slate-800">Dec 15-22, 2025</p>
                </div>
              </div>

              {/* Budget */}
              <div className="flex gap-4">
                <div className="bg-blue-50 p-2.5 rounded-lg h-fit">
                  <DollarSign className="text-blue-600 w-5 h-5" />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">Budget</p>
                  <p className="font-semibold text-slate-800">$4,000 - $5,000</p>
                </div>
              </div>

              {/* Destination */}
              <div className="flex gap-4">
                <div className="bg-blue-50 p-2.5 rounded-lg h-fit">
                  <MapPin className="text-blue-600 w-5 h-5" />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1">Destination</p>
                  <p className="font-semibold text-slate-800">Egypt <span className="font-normal text-gray-500 text-sm">(Not specific yet)</span></p>
                </div>
              </div>

              {/* Interests - Spans full width on mobile, standard on desktop */}
              <div className="flex gap-4 md:col-span-2 items-start mt-2">
                <div className="bg-blue-50 p-2.5 rounded-lg h-fit shrink-0">
                  <Heart className="text-blue-600 w-5 h-5" />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Interests</p>
                  <div className="flex flex-wrap gap-2">
                    {["History", "Photography", "Local Food", "Adventure"].map((tag) => (
                      <span key={tag} className="bg-blue-50 text-blue-700 px-4 py-1.5 rounded-full text-sm font-medium border border-blue-100">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Live Transcript Panel - Only shown during active call */}
          {isCallActive && (
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
              <div className="flex items-center gap-2 mb-4">
                <div className="p-1.5 bg-red-100 rounded-full">
                  <Mic className="w-5 h-5 text-red-600 animate-pulse" />
                </div>
                <h2 className="text-xl font-bold text-slate-800">Live Transcript</h2>
                <span className="ml-auto text-xs text-slate-500">
                  {transcripts.length} segment{transcripts.length !== 1 ? 's' : ''}
                </span>
              </div>

              <div className="max-h-60 overflow-y-auto space-y-3 bg-slate-50 rounded-xl p-4">
                {transcripts.length === 0 ? (
                  <div className="text-center py-8 text-slate-400">
                    <Mic className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Listening for speech...</p>
                  </div>
                ) : (
                  transcripts.map((transcript, index) => (
                    <div key={index} className="bg-white p-3 rounded-lg border border-slate-200 shadow-sm">
                      <div className="flex justify-between items-start mb-1">
                        <span className="text-xs font-medium text-blue-600">Segment {transcript.segment}</span>
                        <span className="text-xs text-slate-400">{transcript.timestamp}</span>
                      </div>
                      <p className="text-sm text-slate-700">{transcript.text}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* 2. Ask Client Section */}
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
            <div className="flex items-center gap-2 mb-6">
              <div className="p-1.5 bg-orange-100 rounded-full">
                <AlertCircle className="w-5 h-5 text-orange-600" />
              </div>
              <h2 className="text-xl font-bold text-slate-800">Ask Client</h2>

              {/* Refresh button */}
              {currentCallIdRef.current && (
                <button
                  onClick={() => fetchProfileQuestions(currentCallIdRef.current)}
                  disabled={questionsLoading}
                  className="ml-auto p-2 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50"
                  title="Refresh questions"
                >
                  <RefreshCw className={`w-4 h-4 text-slate-500 ${questionsLoading ? 'animate-spin' : ''}`} />
                </button>
              )}
            </div>

            <div className="space-y-4">
              {/* Loading state */}
              {questionsLoading && profileQuestions.length === 0 && (
                <div className="text-center py-8 text-slate-400">
                  <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" />
                  <p className="text-sm">Loading questions...</p>
                </div>
              )}

              {/* Error state */}
              {questionsError && (
                <div className="border border-red-200 bg-red-50 p-4 rounded-xl">
                  <p className="text-red-700 text-sm">{questionsError}</p>
                </div>
              )}

              {/* Empty state - no questions available */}
              {!questionsLoading && !questionsError && profileQuestions.length === 0 && (
                <div className="text-center py-8 text-slate-400 border border-dashed border-slate-200 rounded-xl">
                  <MessageCircleQuestion className="w-10 h-10 mx-auto mb-3 opacity-50" />
                  <p className="text-sm font-medium text-slate-500">No questions available</p>
                  <p className="text-xs text-slate-400 mt-1">
                    {isCallActive
                      ? "Questions will appear as the profile is built"
                      : "Start a call to generate profile questions"}
                  </p>
                </div>
              )}

              {/* Dynamic questions from API */}
              {profileQuestions.map((question, index) => {
                // Alternate colors based on index
                const colorSchemes = [
                  { border: 'border-orange-200', bg: 'bg-[#FFFBF0]', textColor: 'text-orange-700/80', badgeBg: 'bg-orange-200', badgeText: 'text-orange-800' },
                  { border: 'border-amber-200', bg: 'bg-[#FFFEF0]', textColor: 'text-amber-700/80', badgeBg: 'bg-amber-200', badgeText: 'text-amber-800' },
                  { border: 'border-blue-200', bg: 'bg-[#F0F7FF]', textColor: 'text-blue-700/80', badgeBg: 'bg-blue-200', badgeText: 'text-blue-800' },
                  { border: 'border-purple-200', bg: 'bg-[#F5F0FF]', textColor: 'text-purple-700/80', badgeBg: 'bg-purple-200', badgeText: 'text-purple-800' },
                ];
                const scheme = colorSchemes[index % colorSchemes.length];

                return (
                  <div
                    key={index}
                    className={`border ${scheme.border} ${scheme.bg} p-5 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-3 hover:shadow-md transition-shadow cursor-pointer`}
                  >
                    <div>
                      <h3 className="font-bold text-slate-800 text-lg mb-1">"{question.question}"</h3>
                      <p className={`${scheme.textColor} text-sm font-medium`}>
                        Fields: {question.fields_filling?.join(', ') || 'General'}
                      </p>
                    </div>
                    <span className={`${scheme.badgeBg} ${scheme.badgeText} text-xs font-bold px-3 py-1.5 rounded whitespace-nowrap`}>
                      Question {index + 1}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right Column (Span 1) - AI Suggestions */}
        <div className="lg:col-span-1">
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 h-full">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-amber-500" />
                <h2 className="text-xl font-bold text-slate-800">AI Suggestions</h2>
              </div>
              {recommendations?.lastUpdated && (
                <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded-full flex items-center gap-1">
                  <RefreshCw className="w-3 h-3" />
                  Updated {recommendations.lastUpdated}
                </span>
              )}
            </div>

            <div className="space-y-4">
              {/* Loading/Empty state */}
              {!recommendations && (
                <div className="text-center py-8 text-slate-400 border border-dashed border-slate-200 rounded-xl">
                  <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-50" />
                  <p className="text-sm font-medium text-slate-500">Waiting for recommendations</p>
                  <p className="text-xs text-slate-400 mt-1">
                    {isCallActive
                      ? "Recommendations will appear as we learn more about your trip"
                      : "Start a call to get personalized suggestions"}
                  </p>
                </div>
              )}

              {/* Hotel Recommendation */}
              {recommendations?.hotel && (
                <div className="border border-gray-100 rounded-xl p-5 hover:border-blue-200 hover:shadow-lg transition-all cursor-pointer group">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex items-center gap-2">
                      <Hotel className="w-4 h-4 text-blue-600" />
                      <h3 className="font-bold text-slate-800 text-lg group-hover:text-blue-700 transition-colors">
                        {recommendations.hotel.name || 'Recommended Hotel'}
                      </h3>
                    </div>
                    <span className="bg-blue-100 text-blue-700 text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider">Hotel</span>
                  </div>
                  {recommendations.hotel.location && (
                    <p className="text-sm text-gray-500 mb-2 flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      {recommendations.hotel.location}
                    </p>
                  )}
                  {recommendations.hotel.description && (
                    <p className="text-sm text-gray-500 mb-4 leading-relaxed line-clamp-2">
                      {recommendations.hotel.description}
                    </p>
                  )}
                  <div className="flex justify-between items-center pt-2 border-t border-gray-50">
                    <p className="text-sm font-semibold text-slate-600">
                      {recommendations.hotel.price ? `~${recommendations.hotel.price}/night` : 'Price TBD'}
                    </p>
                    <MoreHorizontal className="text-gray-400 w-5 h-5" />
                  </div>
                </div>
              )}

              {/* Activities from Itinerary */}
              {recommendations?.itinerary && Object.entries(recommendations.itinerary).slice(0, 2).map(([day, activities]) => (
                activities.filter(item => item.type === 'activity').slice(0, 2).map((activity, idx) => (
                  <div key={`${day}-${idx}`} className="border border-gray-100 rounded-xl p-5 hover:border-green-200 hover:shadow-lg transition-all cursor-pointer group">
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="font-bold text-slate-800 text-lg group-hover:text-green-700 transition-colors">
                        {activity.name || 'Activity'}
                      </h3>
                      <span className="bg-green-100 text-green-700 text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider">
                        {activity.category || day}
                      </span>
                    </div>
                    {activity.description && (
                      <p className="text-sm text-gray-500 mb-4 leading-relaxed line-clamp-2">
                        {activity.description}
                      </p>
                    )}
                    <div className="flex justify-between items-center pt-2 border-t border-gray-50">
                      <p className="text-sm font-semibold text-slate-600">
                        {activity.price ? `~${activity.price}` : 'Free'}
                      </p>
                      <MoreHorizontal className="text-gray-400 w-5 h-5" />
                    </div>
                  </div>
                ))
              ))}

              {/* Budget Summary */}
              {recommendations?.budget_breakdown && (
                <div className="border border-gray-100 rounded-xl p-4 bg-gradient-to-br from-amber-50 to-orange-50">
                  <div className="flex items-center gap-2 mb-3">
                    <DollarSign className="w-4 h-4 text-amber-600" />
                    <span className="font-semibold text-slate-700">Budget Breakdown</span>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Hotel</span>
                      <span className="font-medium">${Math.round(recommendations.budget_breakdown.hotel_total || 0)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Activities</span>
                      <span className="font-medium">${Math.round(recommendations.budget_breakdown.activities_total || 0)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Food</span>
                      <span className="font-medium">${Math.round(recommendations.budget_breakdown.food_total || 0)}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};

export default TravelDashboard;