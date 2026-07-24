import React, { useState } from 'react';
import { FileText, ChevronDown, ChevronUp, Copy, Youtube, Clock, ExternalLink } from 'lucide-react';

const SourceCitation = ({ sources = [], citationSummary = '' }) => {
  const [expanded, setExpanded] = useState(false);

  if (!Array.isArray(sources) || sources.length === 0) return null;

  // Helper function to check if string is a URL
  const isURL = (str) => {
    try {
      return str && (str.startsWith('http://') || str.startsWith('https://'));
    } catch {
      return false;
    }
  };

  return (
    <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl p-3 shadow-[4px_4px_8px_#b8b9be,-4px_-4px_8px_#ffffff]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full text-left transition-all duration-200 hover:opacity-80"
      >
        <div className="flex items-center space-x-2">
          <div className="p-1.5 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff]">
            <FileText className="h-4 w-4 text-gray-600" />
          </div>
          <span className="text-sm font-medium text-gray-800">
            {sources.length} source{sources.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="p-1 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff]">
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-gray-600" />
          ) : (
            <ChevronDown className="h-4 w-4 text-gray-600" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-3 space-y-2">
          {sources.map((src, i) => {
            // map known API fields with safe fallbacks
            const file = src.source_file ?? src.document ?? src.title ?? 'Unknown source';
            const page = src.page_number ?? src.page ?? null;
            const pages = src.pages ?? null;
            const reference = src.reference ?? src.chunk_id ?? `#${i + 1}`;
            const references = src.references ?? null;
            const type = src.source_type ?? 'unknown';
            // const score = typeof src.relevance_score === 'number' ? src.relevance_score : null;
            // const scores = src.relevance_scores ?? null;
            const excerpt = src.excerpt ?? src.text ?? null;
            const youtubeDetails = src.youtube_details ?? null;
            const isYoutube = type === 'youtube' && youtubeDetails && Array.isArray(youtubeDetails);
            const isWebURL = !isYoutube && isURL(file);

            return (
              <div
                key={i}
                className="bg-gradient-to-br from-white to-gray-50 rounded-xl p-3 shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] hover:shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] transition-all duration-200"
              >
                <div className="flex items-start justify-between mb-1">
                  <div className="flex-1">
                    {/* Non-YouTube sources */}
                    {!isYoutube && (
                      <>
                        {/* Web URL sources - make clickable */}
                        {isWebURL ? (
                          <div className="flex items-center gap-2 mb-1">
                            <div className="p-1 rounded-lg bg-gradient-to-br from-blue-50 to-blue-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff]">
                              <ExternalLink className="h-3.5 w-3.5 text-blue-600" />
                            </div>
                            <a
                              href={file}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline transition-colors duration-200 break-all"
                            >
                              {file}
                            </a>
                          </div>
                        ) : (
                          <div className="text-sm font-medium text-gray-900 mb-1">{file}</div>
                        )}
                        <div className="text-xs text-gray-600">
                          {type} 
                          {references ? ` • Refs: ${references.join(', ')}` : reference ? ` • Ref: ${reference}` : ''}
                          {pages ? ` • Page${pages.length > 1 ? 's' : ''}: ${pages.join(', ')}` : page ? ` • Page ${page}` : ''}
                          {/* {scores && scores.length > 0 ? ` • avg score: ${(scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(3)}` : score ? ` • score: ${score.toFixed(3)}` : ''} */}
                        </div>
                      </>
                    )}

                    {/* YouTube sources - show main URL and timestamp chips */}
                    {isYoutube && (
                      <div className="space-y-2">
                        {/* Main YouTube URL */}
                        <div className="flex items-center gap-2">
                          <div className="p-1 rounded-lg bg-gradient-to-br from-red-50 to-red-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff]">
                            <Youtube className="h-3.5 w-3.5 text-red-600" />
                          </div>
                          <a
                            href={youtubeDetails[0]?.timestamp_url?.split('&t=')[0] || file}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline transition-colors duration-200 break-all"
                          >
                            {file}
                          </a>
                        </div>
                        
                        {/* Timestamp chips in horizontal row */}
                        <div className="flex flex-wrap gap-2 items-center">
                          <Clock className="ms-1 h-3.5 w-3.5 text-gray-500 flex-shrink-0" />
                          {youtubeDetails.map((detail, idx) => (
                            <a
                              key={idx}
                              href={detail.timestamp_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-2 py-1 rounded-lg text-xs font-medium text-gray-700 bg-gradient-to-br from-gray-50 to-gray-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] hover:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] hover:text-blue-600 transition-all duration-200"
                            >
                              {detail.timestamp_display}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 ml-2">
                    <button
                      onClick={() => {
                        try {
                          navigator.clipboard?.writeText(JSON.stringify(src));
                          // optionally show toast/tooltip here
                        } catch (e) {
                          console.warn('copy failed', e);
                        }
                      }}
                      className="p-1.5 rounded-lg text-xs bg-gradient-to-br from-gray-50 to-gray-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] hover:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] active:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] transition-all duration-200"
                      title="Copy source object"
                    >
                      <Copy className="h-3.5 w-3.5 text-gray-600" />
                    </button>
                  </div>
                </div>

                {excerpt && !isYoutube && (
                  <div className="mt-2 p-2 rounded-lg bg-gradient-to-br from-blue-50 to-blue-100 shadow-[inset_2px_2px_4px_rgba(0,0,0,0.05)]">
                    <p className="text-xs text-gray-700 italic">"{excerpt}"</p>
                  </div>
                )}
              </div>
            );
          })}

          {citationSummary && (
            <div className="mt-3 p-3 rounded-xl bg-gradient-to-br from-gray-50 to-gray-100 shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff]">
              <div className="text-xs text-gray-700">
                <strong className="text-gray-900">Citation summary:</strong> {citationSummary}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SourceCitation;