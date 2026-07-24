import React from 'react';
import { MessageSquare, FileText, Zap, Shield, PlusCircle } from 'lucide-react';

const WelcomeScreen = ({ onSendMessage, documents = [], onNewChat, userName }) => {
  // Default suggestions when no documents are uploaded
  const defaultSuggestions = [
    "What are the main topics covered in the documents?",
    "Summarize the key points from all documents",
    "Find information about [specific topic]",
    "Compare information across documents"
  ];

  // Dynamic suggestions based on document names and types
  const getDynamicSuggestions = () => {
    if (!documents || documents.length === 0) {
      return defaultSuggestions;
    }

    // Group documents by type
    const fileDocs = documents.filter(doc => doc.type === 'file');
    const linkDocs = documents.filter(doc => doc.type === 'link');
    const textDocs = documents.filter(doc => doc.type === 'text');
    const driveDocs = documents.filter(doc => doc.type === 'drive');

    // Get names for each type
    const fileNames = fileDocs.map(doc => doc.filename || 'file').slice(0, 2);
    const linkNames = linkDocs.map(doc => doc.filename || 'web page').slice(0, 2);
    const textNames = textDocs.map(doc => doc.filename || 'text document').slice(0, 2);
    const driveNames = driveDocs.map(doc => doc.filename || 'Google Drive document').slice(0, 2);

    // Create dynamic suggestions based on content types
    const suggestions = [];

    if (fileNames.length > 0) {
      suggestions.push(`Summarize the key points from ${fileNames.join(' and ')}`);
    }

    if (linkNames.length > 0) {
      // Check if it's a YouTube video or regular web page
      const firstLink = linkDocs[0];
      if (firstLink.sourceType === "youtube") {
        suggestions.push(`What are the main points discussed in the YouTube video "${firstLink.filename || 'video'}"?`);
        suggestions.push(`Create a summary of the YouTube video "${firstLink.filename || 'video'}"`);
      } else {
        suggestions.push(`What are the main topics in ${linkNames[0]}?`);
        suggestions.push(`Summarize the content of ${linkNames[0]}`);
      }
    }

    if (textNames.length > 0) {
      suggestions.push(`Find specific information about [topic] in ${textNames[0]}`);
    }

    if (driveNames.length > 0) {
      suggestions.push(`Compare ${driveNames.join(' and ')}`);
    }

    // Add a general question if we have multiple types
    if (documents.length > 1) {
      suggestions.push("What are the common themes across all my sources?");
    }

    // Fill in with default suggestions if we don't have enough
    while (suggestions.length < 4) {
      const remainingDefaults = defaultSuggestions.filter(s => !suggestions.includes(s));
      if (remainingDefaults.length > 0) {
        suggestions.push(remainingDefaults[0]);
      } else {
        break;
      }
    }

    return suggestions.slice(0, 4);
  };

  const suggestions = getDynamicSuggestions();

  // Get document type summary
  const getDocumentTypeSummary = () => {
    if (!documents || documents.length === 0) return "";

    // Count document types
    const fileCount = documents.filter(doc => doc.type === 'file').length;
    const textCount = documents.filter(doc => doc.type === 'text').length;
    const driveCount = documents.filter(doc => doc.type === 'drive').length;

    // For links, separate YouTube videos from web pages
    const linkDocs = documents.filter(doc => doc.type === 'link');
    const youtubeCount = linkDocs.filter(doc => doc.sourceType === 'youtube').length;
    const webPageCount = linkDocs.filter(doc => doc.sourceType === 'webpage').length;

    const summaries = [];
    if (fileCount > 0) summaries.push(`${fileCount} file${fileCount > 1 ? 's' : ''}`);
    if (webPageCount > 0) summaries.push(`${webPageCount} web page${webPageCount > 1 ? 's' : ''}`);
    if (youtubeCount > 0) summaries.push(`${youtubeCount} YouTube video${youtubeCount > 1 ? 's' : ''}`);
    if (textCount > 0) summaries.push(`${textCount} text document${textCount > 1 ? 's' : ''}`);
    if (driveCount > 0) summaries.push(`${driveCount} Google Drive document${driveCount > 1 ? 's' : ''}`);

    return summaries.join(', ');
  };

  return (
    <div className="flex-1 flex items-center justify-center p-4 md:p-8 bg-gradient-to-br from-gray-50 to-gray-100 overflow-y-auto">
      <div className="max-w-3xl w-full text-center">
        {/* Welcome Message */}
        <div className="mb-3">
          <div className="inline-block p-4 rounded-2xl bg-gradient-to-br from-gray-50 to-gray-100 shadow-[8px_8px_16px_#b8b9be,-8px_-8px_16px_#ffffff] mb-3">
            <MessageSquare className="h-8 w-8 text-blue-500 mx-auto" />
          </div>
          <h2 className="text-2xl font-bold text-gray-900 mb-3">
            {documents.length > 0
              ? `Welcome, ${userName}!`
              : `Welcome, ${userName}!`}
          </h2>
          <p className="text-gray-600 text-lg">
            {documents.length > 0
              ? "Add files, links, text, or YouTube links to get started"
              : "Add files, links, text, or YouTube links to get started"}
          </p>
        </div>

        {/* Features with Neumorphic Style */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 mb-2 px-18">

          <div className="p-8 rounded-2xl #f0f0f3 border border-blue-300">
            <FileText className="h-10 w-10 text-blue-500 mx-auto mb-4" />
            <h3 className="font-semibold text-black text-lg mb-2">Multiple Sources</h3>
            <p className="text-sm text-gray-700">Upload files, add links, paste text, or Youtube links</p>
          </div>

          <div className="p-8 rounded-2xl #f0f0f3 border border-yellow-300">
            <Zap className="h-10 w-10 text-yellow-500 mx-auto mb-4" />
            <h3 className="font-semibold text-black text-lg mb-2">Instant Answers</h3>
            <p className="text-sm text-gray-700">Get accurate responses in seconds</p>
          </div>

          <div className="p-8 rounded-2xl #f0f0f3 border border-green-300">
            <Shield className="h-10 w-10 text-green-500 mx-auto mb-4" />
            <h3 className="font-semibold text-black text-lg mb-2">Source Citations</h3>
            <p className="text-sm text-gray-700">Every answer includes references</p>
          </div>

        </div>

        {/* Suggested Questions with Neumorphic Inset Style */}
        <div>
          <h3 className="text-lg font-semibold text-gray-900 mb-3">
            {documents.length > 0 ? "Try asking about your sources:" : "Try asking:"}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {suggestions.map((suggestion, index) => (
              <button
                key={index}
                onClick={() => onSendMessage(suggestion)}
                className="p-4 text-left rounded-lg border border-gray-200 bg-white hover:bg-gray-100 transition-all text-sm text-gray-800 font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={documents.length === 0}
              >
                {suggestion}
              </button>
            ))}
          </div>

        </div>

        {documents.length === 0 && (
          <div className="mt-8 p-4 bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl shadow-[inset_4px_4px_8px_#b8b9be,inset_-4px_-4px_8px_#ffffff]">
            <p className="text-yellow-700 text-sm font-medium">
              <strong>Note:</strong> Add at least one source (file, link, text, or Google Drive) to start chatting
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default WelcomeScreen;