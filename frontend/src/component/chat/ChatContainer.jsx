import React, { useState, useEffect, useRef } from 'react';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import WelcomeScreen from './WelcomeScreen';
import api from '../../services/api';

const ChatContainer = ({ documents = [], selectedDocumentIds = [], onNewChat, collectionName, chatHistory = [], onTriggerFileUpload }) => {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false); 
  const [previousDocuments, setPreviousDocuments] = useState([]);
  const [userName, setUserName] = useState('');
  const [isNewChat, setIsNewChat] = useState(true);
  const abortControllerRef = useRef(null);
  const previousCollectionRef = useRef(null);

  useEffect(() => {
    // Get user name from localStorage
    const name = localStorage.getItem('userName');
    if (name) {
      setUserName(name);
    }
  }, []);

  // Reset messages when collection changes
  useEffect(() => {
    if (previousCollectionRef.current !== collectionName) {
      // Collection has changed, reset messages
      setMessages([]);
      setIsNewChat(true);
      previousCollectionRef.current = collectionName;
    }
  }, [collectionName]);

  useEffect(() => {
    // Load chat history if available
    if (chatHistory.length > 0) {
      // Flatten chat history to message format
      const historyMessages = [];
      chatHistory.forEach(chat => {
        if (chat.messages) {
          historyMessages.push(...chat.messages);
        }
      });
      
      if (historyMessages.length > 0) {
        setMessages(historyMessages);
        setIsNewChat(false);
      }
    } else {
      // If chatHistory is explicitly empty array (not just loading), clear messages
      // But only if we don't have any ongoing messages
      if (chatHistory.length === 0 && !loading) {
        // Don't clear if we're in the middle of a conversation
        // Only clear if we truly have no history for this collection
        if (messages.length === 0 || previousCollectionRef.current !== collectionName) {
          setMessages([]);
          setIsNewChat(true);
        }
      }
    }
    // Don't clear messages when chatHistory is empty - keep current conversation
    // This prevents chat from disappearing when documents are deleted
  }, [chatHistory]);

  useEffect(() => {
    const areDocumentsEqual = (docs1, docs2) => {
      if (docs1.length !== docs2.length) return false;
      return docs1.every((doc1, index) => {
        const doc2 = docs2[index];
        return doc1.id === doc2.id && 
               doc1.filename === doc2.filename && 
               doc1.type === doc2.type && 
               doc1.sourceType === doc2.sourceType &&
               doc1.status === doc2.status &&
               doc1.size === doc2.size &&
               doc1.pages === doc2.pages;
      });
    };

    const documentsChanged = !areDocumentsEqual(previousDocuments, documents);
    
    if (documentsChanged) {
      setPreviousDocuments(documents);
      if (isNewChat && messages.length === 0 && documents.length > 0) {
        setIsNewChat(false);
      }
    }
  }, [documents, previousDocuments, messages.length, isNewChat]);

  const handleNewChatCall = () => {
    setIsNewChat(true);
    setMessages([]);
    if (onNewChat) {
      onNewChat();
    }
  };

  // Function to stop the current response
  const handleStopResponse = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setLoading(false);
      setIsStreaming(false); 
    }
  };

  const handleSendMessage = async (messageText) => {
    if (!messageText.trim()) return;

    const userMessage = {
      id: Date.now(),
      role: "user",
      content: messageText,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);
    setIsStreaming(true); 

    try {
      abortControllerRef.current = new AbortController();
      let accumulatedContent = "";
      let sources = [];
      let citationSummary = "";

      // Use collection name instead of user ID
      const actualCollectionName = collectionName || localStorage.getItem('collectionName');
      const requestData = {
        query: messageText,
        collection_name: actualCollectionName,
        max_chunks: 8,
        max_context_chars: 4000,
        top_k: 10,
        selected_document_ids: selectedDocumentIds,
      };

      // Create a unique ID for the assistant message
      const assistantMessageId = `stream-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      
      await api.streamChatMessage(
        requestData,
        (content) => {
          if (accumulatedContent === "") {
            setLoading(false);
            const tempAssistantMessage = {
              id: assistantMessageId,
              role: "assistant",
              content: "",
              sources: [],
              citation_summary: "",
              timestamp: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, tempAssistantMessage]);
          }
          
          accumulatedContent += content;
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, content: accumulatedContent }
                : msg
            )
          );
        },
        (sourcesData) => {
          sources = sourcesData;
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, sources }
                : msg
            )
          );
        },
        (summary) => {
          citationSummary = summary;
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? { ...msg, citation_summary: citationSummary }
                : msg
            )
          );
        },
        abortControllerRef.current.signal 
      );
      
      // Streaming is complete
      setIsStreaming(false);
      // Mark that this is no longer a new chat after first message
      setIsNewChat(false);
    } catch (err) {
      console.error("Failed to send message:", err);
      setLoading(false);
      setIsStreaming(false); 

      const errorMessage = {
        id: Date.now() + 1,
        role: "assistant",
        content: "Sorry, I encountered an error processing your request.",
        timestamp: new Date().toISOString(),
      };
      
      setMessages((prev) => [...prev, errorMessage]);
    }
  };

  return (
    <div className="h-[calc(98vh-57px)] flex flex-col bg-gradient-to-br from-gray-50 to-gray-100 overflow-hidden relative">
      {documents.length === 0 ? (
        // Welcome screen without documents - now scrollable on mobile
        <div className="flex-1 overflow-y-auto">
          <WelcomeScreen onSendMessage={handleSendMessage} documents={documents} userName={userName} />
        </div>
      ) : messages.length === 0 ? (
        // Welcome screen with documents - now scrollable on mobile
        <>
          <div className="flex-1 overflow-y-auto">
            <WelcomeScreen 
              onSendMessage={handleSendMessage} 
              documents={documents} 
              onNewChat={handleNewChatCall}
              userName={userName}
            />
          </div>
          {/* Show input at bottom with gradient overlay */}
          <div className="relative flex-shrink-0">
            <MessageInput 
              onSend={handleSendMessage} 
              disabled={loading} 
              onNewChat={onNewChat} 
              onTriggerFileUpload={onTriggerFileUpload}
              onStop={handleStopResponse}
              isStreaming={isStreaming}
            />
          </div>
        </>
      ) : (
        <>
          <div className="flex-1 overflow-hidden">
            <MessageList messages={messages} loading={loading} />
          </div>
          <div className="relative flex-shrink-0">
            <MessageInput 
              onSend={handleSendMessage} 
              disabled={loading} 
              onNewChat={onNewChat} 
              onTriggerFileUpload={onTriggerFileUpload}
              onStop={handleStopResponse}
              isStreaming={isStreaming}
            />
          </div>
        </>
      )}
    </div>
  );
};

export default ChatContainer;