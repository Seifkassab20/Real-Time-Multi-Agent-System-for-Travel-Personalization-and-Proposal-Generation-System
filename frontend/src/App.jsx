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
  Mic
} from 'lucide-react';

const WEBSOCKET_URL = 'ws://localhost:8000/ws/stream';

const TravelDashboard = () => {
  const [isCallActive, setIsCallActive] = useState(false);
  const [clientName, setClientName] = useState("");
  const [clientNumber, setClientNumber] = useState("");
  const [callDuration, setCallDuration] = useState(0);
  const [transcripts, setTranscripts] = useState([]);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');

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

        if (message.type === 'transcript') {
          setTranscripts(prev => [...prev, {
            text: message.text,
            segment: message.segment,
            timestamp: new Date().toLocaleTimeString()
          }]);
        } else if (message.type === 'profile_update') {
          console.log('Profile updated:', message.profile);
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
  }, []);

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
            </div>

            <div className="space-y-4">
              {/* Question 1 - High Priority */}
              <div className="border border-orange-200 bg-[#FFFBF0] p-5 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-3 hover:shadow-md transition-shadow cursor-pointer">
                <div>
                  <h3 className="font-bold text-slate-800 text-lg mb-1">"Would you prefer Cairo or Luxor as your base?"</h3>
                  <p className="text-orange-700/80 text-sm font-medium">Missing destination preference</p>
                </div>
                <span className="bg-orange-200 text-orange-800 text-xs font-bold px-3 py-1.5 rounded whitespace-nowrap">High Priority</span>
              </div>

              {/* Question 2 - Medium */}
              <div className="border border-amber-200 bg-[#FFFEF0] p-5 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-3 hover:shadow-md transition-shadow cursor-pointer">
                <div>
                  <h3 className="font-bold text-slate-800 text-lg mb-1">"Any dietary restrictions for restaurants?"</h3>
                  <p className="text-amber-700/80 text-sm font-medium">Optimize dining recommendations</p>
                </div>
                <span className="bg-amber-200 text-amber-800 text-xs font-bold px-3 py-1.5 rounded whitespace-nowrap">Medium</span>
              </div>

              {/* Question 3 - Suggested */}
              <div className="border border-blue-200 bg-[#F0F7FF] p-5 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-3 hover:shadow-md transition-shadow cursor-pointer">
                <div>
                  <h3 className="font-bold text-slate-800 text-lg mb-1">"Are you interested in hot air balloon rides?"</h3>
                  <p className="text-blue-700/80 text-sm font-medium">Based on adventure interest</p>
                </div>
                <span className="bg-blue-200 text-blue-800 text-xs font-bold px-3 py-1.5 rounded whitespace-nowrap">Suggested</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column (Span 1) - AI Suggestions */}
        <div className="lg:col-span-1">
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 h-full">
            <h2 className="text-xl font-bold text-slate-800 mb-6">AI Suggestions</h2>

            <div className="space-y-4">
              {/* Suggestion 1 */}
              <div className="border border-gray-100 rounded-xl p-5 hover:border-green-200 hover:shadow-lg transition-all cursor-pointer group">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-bold text-slate-800 text-lg group-hover:text-green-700 transition-colors">Sunrise at Abu Simbel</h3>
                  <span className="bg-green-100 text-green-700 text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider">Perfect Match</span>
                </div>
                <p className="text-sm text-gray-500 mb-4 leading-relaxed">Private sunrise tour for photographers. Less crowded, stunning light for your portfolio.</p>
                <div className="flex justify-between items-center pt-2 border-t border-gray-50">
                  <p className="text-sm font-semibold text-slate-600">~$180/person</p>
                  <MoreHorizontal className="text-gray-400 w-5 h-5" />
                </div>
              </div>

              {/* Suggestion 2 */}
              <div className="border border-gray-100 rounded-xl p-5 hover:border-blue-200 hover:shadow-lg transition-all cursor-pointer group">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-bold text-slate-800 text-lg group-hover:text-blue-700 transition-colors">Boutique Stay: Sofitel Legend</h3>
                  <span className="bg-blue-100 text-blue-700 text-[10px] font-bold px-2 py-1 rounded uppercase tracking-wider">Recommended</span>
                </div>
                <p className="text-sm text-gray-500 mb-4 leading-relaxed">Historic luxury on the Nile. Authentic Egyptian architecture with modern amenities.</p>
                <div className="flex justify-between items-center pt-2 border-t border-gray-50">
                  <p className="text-sm font-semibold text-slate-600">~$220/night</p>
                  <MoreHorizontal className="text-gray-400 w-5 h-5" />
                </div>
              </div>

              {/* Suggestion 3 */}
              <div className="border border-gray-100 rounded-xl p-5 hover:border-purple-200 hover:shadow-lg transition-all cursor-pointer group">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-bold text-slate-800 text-lg group-hover:text-purple-700 transition-colors">Private Felucca Sunset</h3>
                </div>
                <p className="text-sm text-gray-500 mb-4 leading-relaxed">Traditional sailboat ride. Golden hour photography opportunity on the river.</p>
                <div className="flex justify-between items-center pt-2 border-t border-gray-50">
                  <p className="text-sm font-semibold text-slate-600">~$45/person</p>
                  <MoreHorizontal className="text-gray-400 w-5 h-5" />
                </div>
              </div>

            </div>
          </div>
        </div>

      </div>
    </div>
  );
};

export default TravelDashboard;