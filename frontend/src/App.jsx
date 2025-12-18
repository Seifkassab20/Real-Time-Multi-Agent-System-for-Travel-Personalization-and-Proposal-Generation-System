import React from 'react';
import { 
  User, 
  Calendar, 
  DollarSign, 
  MapPin, 
  Heart, 
  AlertCircle, 
  MoreHorizontal,
  Phone
} from 'lucide-react';

const TravelDashboard = () => {
  return (
    <div className="min-h-screen bg-[#F0F6FF] p-4 md:p-8 font-sans text-slate-800">
      
      {/* --- Top Header --- */}
      <header className="flex flex-col md:flex-row md:items-center justify-between bg-white p-4 rounded-xl shadow-sm mb-6 border border-slate-100">
        <div className="flex items-center gap-4 mb-4 md:mb-0">
          <div className="flex items-center gap-2">
            <div className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
            </div>
            <span className="font-bold text-slate-700">Live Call</span>
            <span className="text-gray-400 font-normal text-sm">15:23</span>
          </div>
          <div className="h-6 w-px bg-gray-200 mx-2 hidden md:block"></div>
          <div className="text-gray-600 text-sm md:text-base">
            Client: <span className="font-semibold text-slate-800">Sarah & John Mitchell</span>
          </div>
        </div>
        <div className="flex gap-3">
          <button className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-blue-700 transition shadow-sm shadow-blue-200 flex items-center gap-2">
            <Phone size={16} />
            Live Call
          </button>
          <button className="bg-gray-50 text-gray-600 px-6 py-2 rounded-lg font-medium hover:bg-gray-100 transition border border-gray-200">
            Planning
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