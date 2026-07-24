// API service for handling different content types
import axios from 'axios';

const API_BASE_URL = 'http://127.0.0.1:8000';
// const API_BASE_URL = 'http://127.0.0.1:8003';

// Create axios instance with default config
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 180000, 
  withCredentials: true, 
  headers: {
    'Content-Type': 'application/json',
  }
});

let refreshingPromise = null;

const refreshToken = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error('Refresh failed');
    }

    const data = await response.json();
    const { access_token } = data;
    localStorage.setItem('authToken', access_token);

    return access_token;
  } catch (error) {
    localStorage.removeItem('authToken');
    localStorage.removeItem('userId');
    localStorage.removeItem('userName');
    localStorage.removeItem('collectionName');
    window.location.href = '/login';
    throw new Error('Session expired. Please log in again.');
  }
};

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry && 
        !originalRequest.url?.includes('/login') && 
        !originalRequest.url?.includes('/refresh')) {
      originalRequest._retry = true;
  
      if (refreshingPromise) {
        try {
          await refreshingPromise;
          return apiClient(originalRequest);
        } catch (refreshError) {
          return Promise.reject(refreshError);
        }
      }
 
      refreshingPromise = refreshToken();
      
      try {
        await refreshingPromise;
        refreshingPromise = null;
        return apiClient(originalRequest);
      } catch (refreshError) {
        refreshingPromise = null;
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

// Create a new collection
export const createCollection = async () => {
  try {
    const response = await apiClient.post('/collections/create');
    return response.data;
  } catch (error) {
    console.error("API Error in createCollection:", error);
    throw handleError(error);
  }
};

// Process file upload
export const processFile = async (formData, onUploadProgress) => {
  try {
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 600000, // 10 minutes for OCR processing
      onUploadProgress: onUploadProgress, // Track upload progress
    };
    const response = await apiClient.post('/upload', formData, config);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Process YouTube URL
export const processYouTubeUrl = async (data) => {
  try {
    const response = await apiClient.post('/youtube', data);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Process web page URL
export const processWebUrl = async (data) => {
  try {
    const response = await apiClient.post('/web/scrape', data);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Process text content
export const processText = async (formData) => {
  try {
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    };
    const response = await apiClient.post('/process_text', formData, config);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Process podcast from various sources
export const processPodcastFromSource = async (formData) => {
  try {
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    };
    const response = await apiClient.post('/podcast/process', formData, config);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Process podcast
export const processPodcast = async (data) => {
  try {
    const config = {
      responseType: 'blob',
      timeout: 120000
    };
    const response = await apiClient.post('/podcast/process-full', data, config);
    
    const audioBlob = new Blob([response.data], { type: 'audio/wav' });
    const audioUrl = URL.createObjectURL(audioBlob);
    
    return {
      audioBlob,
      audioUrl,
      filename: `${data.source_name || 'podcast'}_${data.target_language}.wav`
    };
  } catch (error) {
    if (error.code === 'ECONNABORTED') {
      throw new Error('Podcast generation is taking longer than expected. Please wait...');
    }
    throw handleError(error);
  }
};

// Generate podcast from collection
export const generatePodcastFromCollection = async (data) => {
  try {
    const config = {
      responseType: 'blob',
      timeout: 120000
    };
    const response = await apiClient.post('/podcast/generate-from-collection', data, config);
    
    const audioBlob = new Blob([response.data], { type: 'audio/wav' });
    const audioUrl = URL.createObjectURL(audioBlob);
    
    return {
      audioBlob,
      audioUrl,
      filename: `podcast_${data.target_language}.wav`
    };
  } catch (error) {
    if (error.code === 'ECONNABORTED') {
      throw new Error('Podcast generation is taking longer than expected. Please wait...');
    }
    throw handleError(error);
  }
};

// Process Google Drive document
export const processDrive = async (formData) => {
  try {
    const config = {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    };
    const response = await apiClient.post('/process_drive', formData, config);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Send chat message (streaming)
export const streamChatMessage = async (messageData, onChunk, onSources, onCitationSummary, signal) => {
  const makeRequest = async (token) => {
    return await fetch(`${API_BASE_URL}/rag/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      credentials: 'include',
      body: JSON.stringify(messageData),
      signal,
    });
  };

  try {
    let token = localStorage.getItem('authToken');
    let response = await makeRequest(token);

    // If unauthorized, refresh using the shared refreshToken function
    if (response.status === 401 && !window.location.pathname.includes('/login')) {
      try {
        // Wait if refresh is already in progress
        if (refreshingPromise) {
          await refreshingPromise;
        } else {
          refreshingPromise = refreshToken();
          await refreshingPromise;
          refreshingPromise = null;
        }
        
        // Retry with new token
        token = localStorage.getItem('authToken');
        response = await makeRequest(token);
        
        // If still 401, redirect
        if (response.status === 401) {
          throw new Error('Session expired');
        }
      } catch (refreshError) {
        refreshingPromise = null;
        localStorage.removeItem('authToken');
        localStorage.removeItem('userId');
        localStorage.removeItem('userName');
        localStorage.removeItem('collectionName');
        window.location.href = '/login';
        throw new Error('Session expired. Please log in again.');
      }
    }

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error('ReadableStream not supported in this browser.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.trim() === '') continue;

        try {
          const data = JSON.parse(line);
          if (data.type === 'chunk' && onChunk) {
            onChunk(data.content);
          } else if (data.type === 'sources' && onSources) {
            onSources(data.sources_used || []);
          }
        } catch (e) {
          console.warn('Error parsing stream chunk:', e);
        }
      }
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      return;
    }
    throw new Error(`Stream error: ${error.message}`);
  }
};


// Get chat history
export const getChatHistory = async (userId, chatId) => {
  try {
    const response = await apiClient.get(`/chat/history/${userId}/${chatId}`);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// User login
export const login = async (email, password) => {
  try {
    const response = await apiClient.post('/login', { email, password });
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// User logout
export const logout = async () => {
  try {
    const response = await apiClient.post('/logout');
    // Clear local storage
    localStorage.removeItem('authToken');
    localStorage.removeItem('userId');
    localStorage.removeItem('userName');
    localStorage.removeItem('collectionName');
    return response.data;
  } catch (error) {
    // Even if logout fails, clear local data
    localStorage.removeItem('authToken');
    localStorage.removeItem('userId');
    localStorage.removeItem('userName');
    localStorage.removeItem('collectionName');
    throw handleError(error);
  }
};

// Fetch documents for a collection
export const fetchDocuments = async (collectionName) => {
  try {
    const response = await apiClient.get(`/api/documents?collection_name=${collectionName}`);
    if (!response || !response.data) {
      console.warn("API response doesn't contain data:", response);
      return { documents: [] };
    }
    
    // Check if response data has documents array
    if (!response.data.documents) {
      console.warn("API response data doesn't contain documents property:", response.data);
      return { documents: [] };
    }
    
    if (!Array.isArray(response.data.documents)) {
      console.warn("API response documents is not an array:", response.data.documents);
      return { documents: [] };
    }
    return response.data;
  } catch (error) {
    console.error("API Error in fetchDocuments:", error);
    console.error("Error details:", {
      message: error.message,
      code: error.code,
      response: error.response?.data,
      status: error.response?.status
    });
    throw handleError(error);
  }
};

// Delete a document from a collection
export const deleteDocument = async (collectionName, documentId) => {
  try {
    const response = await apiClient.delete(`/api/documents?collection_name=${collectionName}&document_id=${documentId}`);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Delete a collection and all its data
export const deleteCollection = async (collectionName) => {
  try {
    const response = await apiClient.delete(`/api/chat/history-delete?collection_name=${collectionName}`);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Fetch chat history for a collection
export const fetchChatHistory = async (collectionName) => {
  try {
    const response = await apiClient.get(`/api/chat/history?collection_name=${collectionName}`);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Fetch all collections for the user
export const fetchCollections = async () => {
  try {
    const response = await apiClient.get('/collections/');
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Add speech-to-text function
export const speechToText = async (audioBlob) => {
  try {
    const formData = new FormData();
    formData.append('audio', audioBlob);

    const config = {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    };

    const response = await apiClient.post('/chat/stt', formData, config);
    return response.data;
  } catch (error) {
    throw handleError(error);
  }
};

// Error handling helper
const handleError = (error) => {
  if (error.code === 'ECONNABORTED') {
    return new Error('Request timeout. The operation is taking longer than expected. Please try again.');
  }
  
  if (error.response) {
    const errorMessage = error.response.data?.detail || 
                        error.response.data?.message || 
                        `Server error: ${error.response.status}`;
    
    if (error.response.status === 401 && errorMessage) {
      return new Error(errorMessage);
    } else if (error.response.status === 401) {
      return new Error('Session expired. Please log in again.');
    }
    
    return new Error(errorMessage);
  } else if (error.request) {
    return new Error('No response from server. Check your connection or try again later.');
  } else {
    return new Error(error.message);
  }
};

// Export all functions
export default {
  createCollection,
  processFile,
  processYouTubeUrl,
  processWebUrl,
  processText,
  processPodcastFromSource,
  processDrive,
  processPodcast,
  generatePodcastFromCollection,
  streamChatMessage,
  getChatHistory,
  login,
  logout,
  fetchDocuments,
  deleteDocument,
  deleteCollection,
  fetchChatHistory,
  fetchCollections,
  speechToText
};