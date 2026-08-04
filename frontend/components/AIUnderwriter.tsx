import { useState, useEffect } from "react";
import { analyzePolicy, chatPolicy, ApiError } from "@/lib/api";
import { SimulatePolicyResponse } from "@/lib/types";
import { MessageSquare, Send, Sparkles, Loader2, FileText, AlertCircle, Bot, User } from "lucide-react";

export function AIUnderwriter({ result }: { result: SimulatePolicyResponse }) {
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(true);
  
  const [messages, setMessages] = useState<{role: "user" | "ai", text: string}[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoadingAnalysis(true);
    setAnalysisError(null);
    setAnalysis(null);

    analyzePolicy(result)
      .then((res) => {
        if (mounted) {
          setAnalysis(res.analysis);
          setLoadingAnalysis(false);
        }
      })
      .catch((err: unknown) => {
        if (mounted) {
          const errMsg = err instanceof ApiError 
            ? err.message 
            : err instanceof Error 
            ? err.message 
            : "Failed to connect to AI server.";
          setAnalysisError(errMsg);
          setLoadingAnalysis(false);
        }
      });

    return () => { mounted = false; };
  }, [result]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;
    
    const userMsg = chatInput.trim();
    setMessages(prev => [...prev, { role: "user", text: userMsg }]);
    setChatInput("");
    setChatLoading(true);
    
    try {
      const res = await chatPolicy(result, userMsg);
      setMessages(prev => [...prev, { role: "ai", text: res.reply }]);
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Unable to reach AI backend.";
      setMessages(prev => [...prev, { role: "ai", text: `Error: ${msg}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="bg-slate-950 text-white p-6 rounded-2xl border border-slate-800 shadow-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="bg-amber-500/20 p-2.5 rounded-xl border border-amber-500/30">
            <Sparkles className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h3 className="font-bold text-base text-slate-100 flex items-center gap-2">
              <span>Groq AI Underwriter Dashboard</span>
              <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-amber-400/10 text-amber-400 border border-amber-400/30 uppercase">
                LLaMA 3.3 70B
              </span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">Real-time Actuarial Analysis & Interactive Risk Policy Advisor</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        
        {/* Left Column: Analysis Report */}
        <div className="lg:col-span-7 space-y-3 flex flex-col">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-emerald-400">
            <FileText className="w-4 h-4" />
            <span>Automated Actuarial & Optimization Report</span>
          </div>
          
          <div className="flex-1 bg-slate-900/90 rounded-xl p-4 text-xs text-slate-200 leading-relaxed border border-slate-800 max-h-80 overflow-y-auto font-sans scrollbar-thin scrollbar-thumb-slate-700">
            {loadingAnalysis && (
              <div className="flex items-center gap-3 text-amber-400/90 py-6 justify-center">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span className="font-medium text-xs">Analyzing policy metrics via Groq ultra-low latency LLM...</span>
              </div>
            )}

            {analysisError && (
              <div className="bg-red-950/50 border border-red-800/80 rounded-lg p-3.5 space-y-1.5 text-red-200">
                <div className="flex items-center gap-2 font-bold text-xs text-red-400">
                  <AlertCircle className="w-4 h-4" />
                  <span>AI Analysis Unavailable</span>
                </div>
                <p className="text-[11px] leading-relaxed text-red-300/90">{analysisError}</p>
                <p className="text-[10px] text-red-400/70 font-mono mt-1">
                  Ensure `GROQ_API_KEY` is set in your backend `.env` file.
                </p>
              </div>
            )}

            {analysis && !loadingAnalysis && (
              <div className="whitespace-pre-wrap space-y-2 text-slate-200 font-sans leading-relaxed">
                {analysis}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Chat Interface */}
        <div className="lg:col-span-5 space-y-3 flex flex-col">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-sky-400">
            <MessageSquare className="w-4 h-4" />
            <span>Ask the Underwriter</span>
          </div>
          
          <div className="flex-1 bg-slate-900/90 rounded-xl border border-slate-800 p-3.5 flex flex-col h-80">
            <div className="flex-1 overflow-y-auto space-y-2.5 mb-3 pr-1 text-xs">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center p-4 space-y-2 text-slate-500">
                  <Bot className="w-8 h-8 text-slate-700" />
                  <p className="text-xs">Ask any question about this policy quote</p>
                  <div className="flex flex-wrap gap-1.5 justify-center mt-2">
                    <button
                      type="button"
                      onClick={() => setChatInput("Why is the premium set at this rate?")}
                      className="text-[10px] bg-slate-800/80 hover:bg-slate-800 text-slate-300 px-2 py-1 rounded border border-slate-700 text-left transition-colors"
                    >
                      "Why is the premium set at this rate?"
                    </button>
                    <button
                      type="button"
                      onClick={() => setChatInput("How can we lower the basis risk?")}
                      className="text-[10px] bg-slate-800/80 hover:bg-slate-800 text-slate-300 px-2 py-1 rounded border border-slate-700 text-left transition-colors"
                    >
                      "How can we lower the basis risk?"
                    </button>
                  </div>
                </div>
              ) : (
                messages.map((m, i) => (
                  <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    {m.role === 'ai' && <Bot className="w-4 h-4 text-sky-400 shrink-0 mt-1" />}
                    <div className={`text-xs px-3 py-2 rounded-xl max-w-[85%] leading-relaxed ${
                      m.role === 'user' 
                        ? 'bg-amber-500 text-slate-950 font-semibold rounded-tr-none' 
                        : 'bg-slate-800 text-slate-200 border border-slate-700/80 rounded-tl-none'
                    }`}>
                      {m.text}
                    </div>
                    {m.role === 'user' && <User className="w-4 h-4 text-amber-400 shrink-0 mt-1" />}
                  </div>
                ))
              )}
              {chatLoading && (
                <div className="flex gap-2 justify-start items-center text-slate-400 text-xs">
                  <Bot className="w-4 h-4 text-sky-400 shrink-0" />
                  <div className="bg-slate-800 px-3 py-2 rounded-xl border border-slate-700/80 flex items-center gap-2">
                    <Loader2 className="w-3 h-3 animate-spin text-amber-400" />
                    <span>Underwriter thinking...</span>
                  </div>
                </div>
              )}
            </div>
            
            <form onSubmit={handleSend} className="flex gap-2 pt-2 border-t border-slate-800">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask about risk, strike, payouts..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500 transition-all"
                disabled={chatLoading}
              />
              <button
                type="submit"
                disabled={chatLoading || !chatInput.trim()}
                className="bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-bold rounded-xl px-3.5 flex items-center justify-center transition-all disabled:opacity-40"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>
        </div>

      </div>
    </div>
  );
}
