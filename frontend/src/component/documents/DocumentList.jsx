// DocumentList.jsx
import React from "react";
import DocumentCard from "./DocumentCard";
import { FileX, Loader } from "lucide-react";

const DocumentList = ({ documents = [], selectedDocumentIds = [], onToggleSelect, onDelete, loading = false }) => {
  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <Loader className="h-6 w-6 animate-spin text-blue-600" />
        <span className="ml-2 text-sm text-gray-600">Loading documents...</span>
      </div>
    );
  }

  if (!documents || documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center">
        <FileX className="h-12 w-12 text-gray-300 mb-3" />
        <p className="text-sm text-gray-500 font-medium">No documents yet</p>
        <p className="text-xs text-gray-400 mt-1">
          Click the + button above to upload your first document
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-2">
      {documents.map((doc) => (
        <DocumentCard 
          key={doc.id} 
          document={doc} 
          isSelected={selectedDocumentIds.includes(doc.id)}
          onToggleSelect={onToggleSelect}
          onDelete={onDelete} 
        />
      ))}
    </div>
  );
};

export default DocumentList;