import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import Layout from './component/layout/Layout';
import ChatContainer from './component/chat/ChatContainer';
import Login from './component/auth/Login';
import api from './services/api';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [chats, setChats] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [currentCollection, setCurrentCollection] = useState(null); // New state for collection
  const [collections, setCollections] = useState([]); // State for all collections
  const navigate = useNavigate();
  
  // Add ref to track if we're intentionally clearing chat (for new chat button)
  const isNewChatRef = useRef(false);
  const previousChatHistoryRef = useRef([]);
  // Add ref to track the current collection to detect changes
  const previousCollectionRef = useRef(null);

  // Check if user is already logged in and validate token
  useEffect(() => {
    const checkAuthStatus = () => {
      const token = localStorage.getItem('authToken');
      if (token) {
        setIsAuthenticated(true);
        const collectionName = localStorage.getItem('collectionName');
        if (collectionName) {
          setCurrentCollection(collectionName);
          previousCollectionRef.current = collectionName;
          fetchDocumentsForCollection(collectionName);
          fetchChatHistoryForCollection(collectionName);
        }
      }
    };

    checkAuthStatus();
    
    const handleStorageChange = (e) => {
      if (e.key === 'authToken') {
        if (e.newValue) {
          setIsAuthenticated(true);
          const collectionName = localStorage.getItem('collectionName');
          if (collectionName) {
            setCurrentCollection(collectionName);
            previousCollectionRef.current = collectionName;
            fetchDocumentsForCollection(collectionName);
            fetchChatHistoryForCollection(collectionName);
          }
        } else {
          setIsAuthenticated(false);
          setDocuments([]);
          setChats([]);
          setCurrentChatId(null);
          setCurrentCollection(null);
          setCollections([]);
          previousCollectionRef.current = null;
          previousChatHistoryRef.current = [];
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  // Auto-select or auto-create collection if logged in but none selected
  useEffect(() => {
    if (isAuthenticated && !currentCollection) {
      const initCollection = async () => {
        try {
          const response = await api.fetchCollections();
          let collectionsData = [];
          
          if (Array.isArray(response)) {
            collectionsData = response;
          } else if (response && Array.isArray(response.collections)) {
            collectionsData = response.collections;
          } else if (response && Array.isArray(response.data)) {
            collectionsData = response.data;
          } else if (response && response.data && Array.isArray(response.data.collections)) {
            collectionsData = response.data.collections;
          }
          
          if (collectionsData.length > 0) {
            // Select the most recent collection
            const mostRecentCollection = collectionsData[0].collection_name || collectionsData[0].name;
            if (mostRecentCollection) {
              previousChatHistoryRef.current = [];
              setCurrentCollection(mostRecentCollection);
              localStorage.setItem('collectionName', mostRecentCollection);
              
              fetchDocumentsForCollection(mostRecentCollection);
              fetchChatHistoryForCollection(mostRecentCollection);
            }
          } else {
            // No collections exist, automatically create one (start a new chat)
            handleNewChat();
          }
        } catch (error) {
          console.error("Failed to auto-initialize collection:", error);
        }
      };
      
      initCollection();
    }
  }, [isAuthenticated, currentCollection]);

  // Add effect to monitor collection name changes
  useEffect(() => {
    if (currentCollection) {
      // Check if this is a different collection
      const collectionChanged = previousCollectionRef.current !== currentCollection;
      
      if (collectionChanged) {
        // Clear previous chat history when switching collections
        previousChatHistoryRef.current = [];
        previousCollectionRef.current = currentCollection;
      }
      
      // Fetch documents and chat history for this collection
      fetchDocumentsForCollection(currentCollection);
      fetchChatHistoryForCollection(currentCollection);
      
      // Reset the new chat flag after a short delay to ensure all updates complete
      const timer = setTimeout(() => {
        isNewChatRef.current = false;
      }, 500);
      
      return () => clearTimeout(timer);
    }
  }, [currentCollection]);

  const fetchDocumentsForCollection = async (collectionName) => {
    try {

      // Validate collection name
      if (!collectionName) {
        console.warn("No collection name provided for document fetching");
        setDocuments([]);
        setSelectedDocumentIds([]);
        return;
      }
      
      const response = await api.fetchDocuments(collectionName);
      // Check if response has documents array
      if (!response) {
        console.warn("No response received from API");
        setDocuments([]);
        setSelectedDocumentIds([]);
        return;
      }
      
      if (!response.documents) {
        console.warn("Response doesn't contain documents property:", response);
        setDocuments([]);
        setSelectedDocumentIds([]);
        return;
      }
      
      if (!Array.isArray(response.documents)) {
        console.warn("Documents property is not an array:", response.documents);
        setDocuments([]);
        setSelectedDocumentIds([]);
        return;
      }

      const serverDocuments = response.documents.map(doc => {

        let sourceType = 'file'; // default
        let type = getFileTypeFromExtension(doc.file_type);
        
        if (doc.source_url) {
          // Check if it's a YouTube URL
          const youtubeRegex = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$/;
          if (youtubeRegex.test(doc.source_url)) {
            sourceType = 'youtube';
          } else {
            sourceType = 'webpage';
          }
          // Set type to 'link' for URLs
          type = 'link';
        }
        
        const processedDoc = {
          id: doc.id,
          filename: doc.file_name || doc.filename || 'Unnamed Document',
          status: 'ready', // Assume ready since they're already processed
          type: type,
          size: null, // Size not provided in API response
          pages: doc.chunk_count || doc.chunks_inserted,
          uploadedAt: doc.uploaded_at,
          sourceType: sourceType,
          url: doc.source_url || null
        };
        return processedDoc;
      });
      setDocuments(serverDocuments);
      setSelectedDocumentIds(serverDocuments.map(doc => doc.id));
    } catch (error) {
      console.error("Failed to fetch documents:", error);
      setDocuments([]); // Clear documents on error for now
      setSelectedDocumentIds([]);
    }
  };

  const fetchChatHistoryForCollection = async (collectionName) => {
    try {
      const response = await api.fetchChatHistory(collectionName);
      
      // Handle the correct response format from the API
      const collectionData = response;
      
      // Convert server chat history to our format
      const historyMessages = [];
      collectionData.messages.forEach(msg => {
        // Add user message
        historyMessages.push({
          id: msg.id,
          role: 'user',
          content: msg.query_text,
          timestamp: msg.created_at
        });
        
        // Add assistant response
        historyMessages.push({
          id: `response-${msg.id}`,
          role: 'assistant',
          content: msg.response_text,
          sources: msg.sources_used || [],
          timestamp: msg.created_at
        });
      });
      
      // Create a chat object with the messages in the format expected by ChatContainer
      if (historyMessages.length > 0) {
        const chatId = `chat-${collectionName}`;
        const newChat = {
          id: chatId,
          title: `Chat from ${new Date(collectionData.messages[0].created_at).toLocaleDateString()}`,
          createdAt: collectionData.messages[0].created_at,
          messages: historyMessages
        };
        
        setChats([newChat]);
        setCurrentChatId(chatId);
        // Update the previous chat history ref
        previousChatHistoryRef.current = [newChat];
      } else if (isNewChatRef.current) {
        // Only clear chat if we're starting a new chat
        setChats([]);
        setCurrentChatId(null);
        previousChatHistoryRef.current = [];
        isNewChatRef.current = false;
      } else {
        // For existing collection with no messages, clear the chat
        setChats([]);
        setCurrentChatId(null);
        previousChatHistoryRef.current = [];
      }
      // Otherwise, keep existing chat state
    } catch (error) {
      console.error("Failed to fetch chat history:", error);
      if (isNewChatRef.current) {
        setChats([]);
        setCurrentChatId(null);
        previousChatHistoryRef.current = [];
        isNewChatRef.current = false;
      }
    }
  };

  // Fetch all collections for the user
  const fetchAllCollections = async () => {
    try {
      const response = await api.fetchCollections();
      
      // Handle the specific response format from the collections API
      let collectionsData = [];
      
      // If response is an array, use it directly
      if (Array.isArray(response)) {
        collectionsData = response;
      } 
      // If response has a collections property that's an array
      else if (response && Array.isArray(response.collections)) {
        collectionsData = response.collections;
      }
      // If response has a data property that's an array
      else if (response && Array.isArray(response.data)) {
        collectionsData = response.data;
      }
      // If response is an object with data.collections
      else if (response && response.data && Array.isArray(response.data.collections)) {
        collectionsData = response.data.collections;
      }
      
      // Transform collections to ensure they have the required properties
      const transformedCollections = collectionsData.map(collection => {
        // Handle the specific format returned by the API
        // Based on your description, the API returns objects with collection_name and collection_id
        return {
          name: collection.name || collection.collection_name || 'Untitled Collection',
          chat_title: collection.chat_title || collection.collection_name,
          created_at: collection.created_at || collection.createdAt || new Date().toISOString(),
          last_message: collection.last_message || collection.lastMessage || ''
        };
      });
      
      setCollections(transformedCollections);
    } catch (error) {
      console.error("Failed to fetch collections:", error);
      setCollections([]);
    }
  };

  // Handle collection selection
  const handleCollectionSelect = async (collectionName) => {
    try {
      // Clear previous chat history when switching collections
      previousChatHistoryRef.current = [];
      
      setCurrentCollection(collectionName);
      localStorage.setItem('collectionName', collectionName);
      
      // Fetch documents and chat history for this collection
      await fetchDocumentsForCollection(collectionName);
      await fetchChatHistoryForCollection(collectionName);
    } catch (error) {
      console.error("Failed to select collection:", error);
    }
  };

  const getFileTypeFromExtension = (fileType) => {
    if (!fileType) return 'file';
    if (fileType.includes('pdf')) return 'file';
    if (fileType.includes('text') || fileType.includes('txt')) return 'text';
    return 'file';
  };

  const handleLogin = () => {
    setIsAuthenticated(true);
    // Retrieve collection name from localStorage
    const collectionName = localStorage.getItem('collectionName');
    if (collectionName) {
      setCurrentCollection(collectionName);
      previousCollectionRef.current = collectionName;
      // Fetch documents and chat history for this collection
      fetchDocumentsForCollection(collectionName);
      fetchChatHistoryForCollection(collectionName);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('userId');
    localStorage.removeItem('userName');
    localStorage.removeItem('collectionName');
    setIsAuthenticated(false);
    setDocuments([]);
    setSelectedDocumentIds([]);
    setChats([]);
    setCurrentChatId(null);
    setCurrentCollection(null);
    setCollections([]);
    previousCollectionRef.current = null;
    previousChatHistoryRef.current = [];
    navigate('/login');
  };

  const handleToggleSelectDocument = (docId) => {
    setSelectedDocumentIds(prev => {
      if (prev.includes(docId)) {
        return prev.filter(id => id !== docId);
      } else {
        return [...prev, docId];
      }
    });
  };

  const handleDocumentUpload = (newDoc) => {
    // Add the new document to the current documents list
    setDocuments(prev => [...prev, newDoc]);
    setSelectedDocumentIds(prev => [...prev, newDoc.id]);
  };

  const handleDocumentDelete = async (docId) => {
    try {
      // Delete document from server
      if (currentCollection) {
        await api.deleteDocument(currentCollection, docId);
      }
      
      // Remove document from local state
      setDocuments(prev => prev.filter(doc => doc.id !== docId));
      setSelectedDocumentIds(prev => prev.filter(id => id !== docId));
      
      // Don't refetch chat history - keep existing chat state
    } catch (error) {
      console.error("Failed to delete document:", error);
      // Even if server deletion fails, remove from local state for better UX
      setDocuments(prev => prev.filter(doc => doc.id !== docId));
      setSelectedDocumentIds(prev => prev.filter(id => id !== docId));
      // Handle error appropriately
    }
  };

  // Handle collection deletion
  const handleCollectionDelete = async (collectionName) => {
    try {
      // Delete collection from server
      await api.deleteCollection(collectionName);
      
      // Remove collection from local state
      setCollections(prev => prev.filter(collection => collection.name !== collectionName));
      
      // If the deleted collection was the current one, clear it from localStorage
      if (currentCollection === collectionName) {
        localStorage.removeItem('collectionName');
        setCurrentCollection(null);
        setChats([]);
        setCurrentChatId(null);
        setDocuments([]);
      }
      
      // Show success message to user
      console.log(`Collection ${collectionName} deleted successfully`);
    } catch (error) {
      console.error("Failed to delete collection:", error);
      // Handle error appropriately
    }
  };

  const handleNewChat = async () => {
    try {
      // Set flag that we're starting a new chat
      isNewChatRef.current = true;
      
      // Clear the previous chat history ref immediately
      previousChatHistoryRef.current = [];
      
      // Create a new collection when starting a new chat
      const collectionResponse = await api.createCollection();
      const newChatId = `chat-${Date.now()}`;
      
      // Clear the current chat state completely
      setChats([]);
      setCurrentChatId(null);
      setDocuments([]);
      setSelectedDocumentIds([]);
      
      const newCollectionName = collectionResponse.collection_name || collectionResponse.name || `collection-${Date.now()}`;
      
      // Update the previous collection ref
      previousCollectionRef.current = newCollectionName;
      
      setCurrentCollection(newCollectionName);
      localStorage.setItem('collectionName', newCollectionName);

      // Fetch documents for the new collection (should be empty)
      await fetchDocumentsForCollection(newCollectionName);
      
      // Also fetch chat history for the new collection (should be empty)
      await fetchChatHistoryForCollection(newCollectionName);
    } catch (error) {
      console.error("Failed to create new chat:", error);
      isNewChatRef.current = false;
    }
  };

  // Get current chat for passing to ChatContainer
  const currentChat = chats.find(chat => chat.id === currentChatId) || null;
  
  // Use useMemo to stabilize chatHistory and prevent unnecessary changes
  const chatHistory = useMemo(() => {
    const newHistory = currentChat ? [currentChat] : [];
    
    // If we're starting a new chat, always return empty
    if (isNewChatRef.current) {
      previousChatHistoryRef.current = [];
      return [];
    }
    
    // If the collection has changed, clear previous history
    if (previousCollectionRef.current !== currentCollection) {
      previousChatHistoryRef.current = [];
      return [];
    }
    
    // If we have a valid chat history, update the ref
    if (newHistory.length > 0) {
      previousChatHistoryRef.current = newHistory;
      return newHistory;
    }
    
    // If new history is empty but we have previous history from the SAME collection, keep it
    // This prevents chat from disappearing during re-renders (like when deleting documents)
    if (previousChatHistoryRef.current.length > 0 && 
        previousChatHistoryRef.current[0]?.id?.includes(currentCollection)) {
      return previousChatHistoryRef.current;
    }
    
    // Otherwise return empty
    previousChatHistoryRef.current = [];
    return newHistory;
  }, [currentChat, chats, currentChatId, currentCollection]);

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" /> : <Login onLogin={handleLogin} />} />
      <Route path="/" element={isAuthenticated ? (
        <Layout 
          documents={documents} 
          selectedDocumentIds={selectedDocumentIds}
          onToggleSelectDocument={handleToggleSelectDocument}
          onDocumentUpload={handleDocumentUpload} 
          onDocumentDelete={handleDocumentDelete}
          chats={chats}
          currentChatId={currentChatId}
          onNewChat={handleNewChat}
          onLogout={handleLogout}
          collectionName={currentCollection} // Make sure this is passed correctly
          collections={collections}
          onCollectionSelect={handleCollectionSelect}
          fetchCollections={fetchAllCollections}
          onCollectionDelete={handleCollectionDelete}
        >
          <ChatContainer 
            key={currentCollection} // Force re-mount when collection changes for fresh state
            documents={documents} 
            selectedDocumentIds={selectedDocumentIds}
            onNewChat={handleNewChat}
            collectionName={currentCollection} // Pass collection name to chat container
            chatHistory={chatHistory} // Use memoized chatHistory
          />
        </Layout>
      ) : (
        <Navigate to="/login" />
      )} />
    </Routes>
  );
}

export default App;