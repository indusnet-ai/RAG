import React, { useRef, useEffect, useState } from 'react';
import { User, Bot, Loader, Copy, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import SourceCitation from './SourceCitation';

const MessageList = ({ messages, loading }) => {
  const messagesEndRef = useRef(null);
  const [copiedCode, setCopiedCode] = useState(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedCode(id);
    setTimeout(() => setCopiedCode(null), 2000);
  };

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-br from-gray-50 to-gray-100">
      <div className="max-w-4xl mx-auto p-4 space-y-6">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
        >
          <div className={`flex space-x-3 max-w-3xl ${message.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''}`}>
            {/* Avatar - Neumorphic style */}
            <div className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff] ${
              message.role === 'user' 
                ? 'bg-gradient-to-br from-blue-500 to-blue-600' 
                : 'bg-gradient-to-br from-gray-50 to-gray-100'
            }`}>
              {message.role === 'user' ? (
                <User className="h-5 w-5 text-white" />
              ) : (
                <Bot className="h-5 w-5 text-gray-600" />
              )}
            </div>

            {/* Message Content */}
            <div className="flex-1 min-w-0">
              {/* Message bubble - Neumorphic style */}
              <div className={`rounded-2xl p-4 ${
                message.role === 'user'
                  ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-[4px_4px_8px_#b8b9be,-2px_-2px_4px_#ffffff]'
                  : 'bg-gradient-to-br from-gray-50 to-gray-100 text-gray-900 shadow-[4px_4px_8px_#b8b9be,-4px_-4px_8px_#ffffff]'
              }`}>
                {message.role === 'user' ? (
                  <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
                ) : (
                  <div className="text-sm markdown-content">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({node, inline, className, children, ...props}) {
                          const match = /language-(\w+)/.exec(className || '');
                          const codeString = String(children).replace(/\n$/, '');
                          const codeId = `${message.id}-${Math.random()}`;

                          return !inline && match ? (
                            <div className="relative group my-4 rounded-lg overflow-hidden shadow-[4px_4px_8px_#b8b9be,-2px_-2px_4px_#ffffff]">
                              <div className="flex items-center justify-between bg-gray-800 px-4 py-2">
                                <span className="text-xs text-gray-300 font-mono">{match[1]}</span>
                                <button
                                  onClick={() => copyToClipboard(codeString, codeId)}
                                  className="flex items-center gap-1 text-xs text-gray-300 hover:text-white transition-colors px-2 py-1 rounded hover:bg-gray-700"
                                >
                                  {copiedCode === codeId ? (
                                    <>
                                      <Check className="h-3 w-3" />
                                      <span>Copied!</span>
                                    </>
                                  ) : (
                                    <>
                                      <Copy className="h-3 w-3" />
                                      <span>Copy code</span>
                                    </>
                                  )}
                                </button>
                              </div>
                              <SyntaxHighlighter
                                style={vscDarkPlus}
                                language={match[1]}
                                PreTag="div"
                                customStyle={{
                                  margin: 0,
                                  padding: '1rem',
                                  fontSize: '0.875rem',
                                  borderTopLeftRadius: 0,
                                  borderTopRightRadius: 0,
                                }}
                                {...props}
                              >
                                {codeString}
                              </SyntaxHighlighter>
                            </div>
                          ) : (
                            <code className="bg-gradient-to-br from-red-50 to-red-100 text-red-600 px-1.5 py-0.5 rounded text-xs font-mono shadow-[inset_1px_1px_2px_rgba(0,0,0,0.1)]" {...props}>
                              {children}
                            </code>
                          );
                        },
                        p({children}) {
                          return <p className="mb-4 last:mb-0 leading-7">{children}</p>;
                        },
                        h1({children}) {
                          return <h1 className="text-2xl font-bold mb-4 mt-6 first:mt-0">{children}</h1>;
                        },
                        h2({children}) {
                          return <h2 className="text-xl font-bold mb-3 mt-5 first:mt-0">{children}</h2>;
                        },
                        h3({children}) {
                          return <h3 className="text-lg font-semibold mb-2 mt-4 first:mt-0">{children}</h3>;
                        },
                        h4({children}) {
                          return <h4 className="text-base font-semibold mb-2 mt-3 first:mt-0">{children}</h4>;
                        },
                        ul({children}) {
                          return <ul className="list-disc list-outside ml-6 mb-4 space-y-1">{children}</ul>;
                        },
                        ol({children}) {
                          return <ol className="list-decimal list-outside ml-6 mb-4 space-y-1">{children}</ol>;
                        },
                        li({children}) {
                          return <li className="leading-7">{children}</li>;
                        },
                        blockquote({children}) {
                          return (
                            <blockquote className="border-l-4 border-blue-400 pl-4 py-2 my-4 italic text-gray-700 bg-gradient-to-br from-blue-50 to-blue-100 rounded-r-lg shadow-[2px_2px_4px_#b8b9be]">
                              {children}
                            </blockquote>
                          );
                        },
                        table({children}) {
                          return (
                            <div className="overflow-x-auto my-4 rounded-lg shadow-[4px_4px_8px_#b8b9be,-2px_-2px_4px_#ffffff]">
                              <table className="min-w-full border-collapse">
                                {children}
                              </table>
                            </div>
                          );
                        },
                        thead({children}) {
                          return <thead className="bg-gradient-to-br from-gray-100 to-gray-200">{children}</thead>;
                        },
                        th({children}) {
                          return (
                            <th className="border border-gray-300 px-4 py-2 text-left font-semibold">
                              {children}
                            </th>
                          );
                        },
                        td({children}) {
                          return (
                            <td className="border border-gray-300 px-4 py-2 bg-white">
                              {children}
                            </td>
                          );
                        },
                        hr() {
                          return <hr className="my-6 border-t-2 border-gray-300 shadow-sm" />;
                        },
                        strong({children}) {
                          return <strong className="font-semibold">{children}</strong>;
                        },
                        em({children}) {
                          return <em className="italic">{children}</em>;
                        },
                      }}
                    >
                      {message.content ? message.content.replace(/<FOLLOW_UP_QUESTIONS>[\s\S]*?<\/FOLLOW_UP_QUESTIONS>/gi, '').trim() : ''}
                    </ReactMarkdown>
                  </div>
                )}
              </div>

              {/* Sources (for assistant messages only) */}
               {message.role === 'assistant' && Array.isArray(message.sources) && message.sources.length > 0 && (
                <div className="mt-2">
                  <SourceCitation sources={message.sources} citationSummary={message.citation_summary} />
                </div>
              )} 

              {/* Timestamp */}
              <p className="text-xs text-gray-500 mt-1">
                {message.timestamp ? new Date(message.timestamp).toLocaleTimeString('en-IN', { hour12: false }) : ''}
              </p>
            </div>
          </div>
        </div>
      ))}

      {/* Loading Indicator - Neumorphic style */}
      {loading && (!messages.length || messages[messages.length - 1].role !== 'assistant' || !messages[messages.length - 1].id.startsWith('stream-')) && (
        <div className="flex justify-start">
          <div className="flex space-x-3 max-w-3xl">
            <div className="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center shadow-[3px_3px_6px_#b8b9be,-3px_-3px_6px_#ffffff]">
              <Bot className="h-5 w-5 text-gray-600" />
            </div>
            <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-4 shadow-[4px_4px_8px_#b8b9be,-4px_-4px_8px_#ffffff]">
              <Loader className="h-5 w-5 animate-spin text-gray-600" />
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
      </div>
    </div>
  );
};

export default MessageList;