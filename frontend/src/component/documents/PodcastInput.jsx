import React, { useState, useEffect } from "react";
import { Mic, AlertCircle, CheckCircle, Loader, FileText } from "lucide-react";
import api from "../../services/api";

const PodcastInput = ({ userId = "55", onAddSuccess, collectionName }) => {
  const [documents, setDocuments] = useState([]);
  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [podcastStyle, setPodcastStyle] = useState("conversational");
  const [targetDuration, setTargetDuration] = useState("5 minutes");
  const [targetLanguage, setTargetLanguage] = useState("English");
  const [loading, setLoading] = useState(false);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [filename, setFilename] = useState(null);
  const [generationTime, setGenerationTime] = useState(null);

  // Fetch documents for the current collection when component mounts
  useEffect(() => {
    const fetchDocuments = async () => {
      const actualCollectionName = collectionName || localStorage.getItem('collectionName');
      
      if (!actualCollectionName) {
        setError("No collection selected. Please select a collection first.");
        return;
      }
      
      setDocumentsLoading(true);
      setSelectedDocuments([]);
      try {
        const response = await api.fetchDocuments(actualCollectionName);
        const docs = response.documents || [];
        setDocuments(docs);
        
        const allDocIds = docs.map(doc => doc.id);
        setSelectedDocuments(allDocIds);
        
        if (docs.length === 0) {
          setError("No documents available in this collection. Please upload documents first.");
        }
      } catch (err) {
        console.error("Failed to fetch documents:", err);
        setError("Failed to load documents: " + err.message);
      } finally {
        setDocumentsLoading(false);
      }
    };

    fetchDocuments();
  }, [collectionName]);

  const handleDocumentToggle = (docId) => {
    setSelectedDocuments(prev => {
      if (prev.includes(docId)) {
        return prev.filter(id => id !== docId);
      } else {
        return [...prev, docId];
      }
    });
  };

  const handleGeneratePodcast = async (e) => {
    e.preventDefault();
    
    const actualCollectionName = collectionName || localStorage.getItem('collectionName');
    
    if (!actualCollectionName) {
      setError("No collection selected. Please select a collection first.");
      return;
    }
    
    if (selectedDocuments.length === 0) {
      setError("Please select at least one document");
      return;
    }
    
    setError(null);
    setSuccess(false);
    setAudioUrl(null);
    setFilename(null);
    setGenerationTime(null);
    setLoading(true);

    const startTime = Date.now();

    try {
      const data = {
        collection_name: actualCollectionName,
        document_ids: selectedDocuments,
        podcast_style: podcastStyle,
        target_duration: targetDuration,
        target_language: targetLanguage
      };
      const response = await api.generatePodcastFromCollection(data);
      
      const endTime = Date.now();
      const timeInSeconds = ((endTime - startTime) / 1000).toFixed(1);
      setGenerationTime(timeInSeconds);
      setAudioUrl(response.audioUrl);
      setFilename(response.filename);
      
      setSuccess(true);
    } catch (err) {
      console.error("Failed to generate podcast:", err);
      setError(err.message || "Failed to generate podcast");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full">
      <form onSubmit={handleGeneratePodcast} className="space-y-3">
        {/* Document Selection */}
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1.5">
            Select Documents
          </label>
          
          {documentsLoading ? (
            <div className="flex justify-center items-center p-3 bg-gray-50 rounded-md border border-gray-200">
              <Loader className="animate-spin h-4 w-4 text-blue-600" />
              <span className="ml-2 text-xs text-gray-600">Loading...</span>
            </div>
          ) : documents.length === 0 ? (
            <div className="text-xs text-gray-500 p-3 text-center bg-gray-50 rounded-md border border-gray-200">
              No documents available
            </div>
          ) : (
            <div className="bg-gray-50 rounded-md max-h-32 overflow-y-auto border border-gray-200">
              {documents.map((doc) => (
                <div 
                  key={doc.id}
                  className={`flex items-center p-2 border-b border-gray-200 last:border-b-0 cursor-pointer hover:bg-gray-100 transition-colors ${
                    selectedDocuments.includes(doc.id) ? 'bg-gray-100' : ''
                  }`}
                  onClick={() => handleDocumentToggle(doc.id)}
                >
                  <input
                    type="checkbox"
                    checked={selectedDocuments.includes(doc.id)}
                    onChange={() => {}}
                    className="h-3 w-3 text-blue-600 rounded mr-2 flex-shrink-0"
                  />
                  <FileText className="h-3 w-3 text-gray-500 mr-1.5 flex-shrink-0" />
                  <span className="text-xs text-gray-700 truncate">{doc.file_name || doc.filename}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Settings Grid */}
        <div className="space-y-2">
          <div>
            <label htmlFor="podcast-style" className="block text-xs font-medium text-gray-700 mb-1">
              Style
            </label>
            <select
              id="podcast-style"
              value={podcastStyle}
              onChange={(e) => setPodcastStyle(e.target.value)}
              disabled={loading}
              className="block w-full px-2 py-1.5 text-xs bg-white border border-gray-300 text-gray-700 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
            >
              <option value="conversational">Conversational</option>
              <option value="interview">Interview</option>
            </select>
          </div>

          <div>
            <label htmlFor="target-duration" className="block text-xs font-medium text-gray-700 mb-1">
              Duration
            </label>
            <select
              id="target-duration"
              value={targetDuration}
              onChange={(e) => setTargetDuration(e.target.value)}
              disabled={loading}
              className="block w-full px-2 py-1.5 text-xs bg-white border border-gray-300 text-gray-700 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
            >
              <option value="2 minutes">2 Minutes</option>
              <option value="5 minutes">5 Minutes</option>
              <option value="10 minutes">10 Minutes</option>
            </select>
          </div>

          <div>
            <label htmlFor="target-language" className="block text-xs font-medium text-gray-700 mb-1">
              Language
            </label>
            <select
              id="target-language"
              value={targetLanguage}
              onChange={(e) => setTargetLanguage(e.target.value)}
              disabled={loading}
              className="block w-full px-2 py-1.5 text-xs bg-white border border-gray-300 text-gray-700 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
            >
              <option value="English">English</option>
              <option value="Tamil">Tamil</option>
              <option value="Odia">Odia</option>
              <option value="Bengali">Bengali</option>
              <option value="Telugu">Telugu</option>
              <option value="Malayalam">Malayalam</option>
              <option value="Kannada">Kannada</option>
              <option value="Gujarati">Gujarati</option>
              <option value="Punjabi">Punjabi</option>
              <option value="Marathi">Marathi</option>
              <option value="Hindi">Hindi</option>
            </select>
          </div>
        </div>

        {/* Generate Button */}
        <button
          type="submit"
          disabled={loading || documentsLoading || selectedDocuments.length === 0}
          className={`w-full flex justify-center items-center py-2 px-3 rounded-md text-xs font-medium transition-colors ${
            loading || documentsLoading || selectedDocuments.length === 0
              ? "bg-blue-500 opacity-50 cursor-not-allowed text-white" 
              : "bg-blue-600 hover:bg-blue-700 text-white"
          }`}
        >
          {loading ? (
            <>
              <Loader className="animate-spin mr-1.5 h-3 w-3" />
              Generating...
            </>
          ) : (
            <>
              <Mic className="mr-1.5 h-3 w-3" />
              Generate Podcast
            </>
          )}
        </button>

        {/* Success Message */}
        {success && audioUrl && (
          <div className="p-2.5 bg-green-50 border border-green-200 rounded-md">
            <div className="flex items-center text-green-700 mb-2">
              <CheckCircle className="h-3.5 w-3.5 mr-1.5 flex-shrink-0" />
              <span className="text-xs font-medium">Podcast ready!</span>
            </div>
            {generationTime && (
              <p className="text-xs text-green-600 mb-2">
                Generated in {generationTime}s
              </p>
            )}
            <div>
              <audio controls className="w-full h-8">
                <source src={audioUrl} type="audio/wav" />
                Your browser does not support the audio element.
              </audio>
            </div>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="p-2.5 bg-red-50 border border-red-200 rounded-md">
            <div className="flex items-start text-red-700">
              <AlertCircle className="h-3.5 w-3.5 mr-1.5 flex-shrink-0 mt-0.5" />
              <span className="text-xs">{error}</span>
            </div>
          </div>
        )}
      </form>
    </div>
  );
};

export default PodcastInput;