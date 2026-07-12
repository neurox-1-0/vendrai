"use client";

import React, { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { IconWell } from '@/components/ui/icon-well';
import { Upload, FileText, CheckCircle2 } from 'lucide-react';
import { motion } from 'framer-motion';

export default function CaseIntake() {
  const [isUploading, setIsUploading] = useState(false);
  const [uploaded, setUploaded] = useState(false);

  const handleUpload = () => {
    setIsUploading(true);
    setTimeout(() => {
      setIsUploading(false);
      setUploaded(true);
    }, 2000);
  };

  return (
    <div className="p-12 h-full flex flex-col">
      <header className="mb-12">
        <h2 className="font-display font-bold text-3xl mb-2">New Vendor Onboarding</h2>
        <p className="text-[var(--color-muted)]">Upload documentation to trigger the agentic analysis pipeline.</p>
      </header>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-12 max-w-6xl">
        {/* Upload Zone */}
        <Card className="flex flex-col items-center justify-center p-12 text-center relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-transparent to-[rgba(108,99,255,0.05)] pointer-events-none" />
          
          <motion.div 
            whileHover={{ scale: 1.05 }}
            className="w-32 h-32 rounded-full shadow-[var(--shadow-extruded)] flex items-center justify-center mb-8 border-4 border-[var(--color-clay)]"
          >
            {uploaded ? (
              <CheckCircle2 className="h-12 w-12 text-[var(--color-success)]" />
            ) : (
              <Upload className="h-12 w-12 text-[var(--color-accent)]" />
            )}
          </motion.div>
          
          <h3 className="font-bold text-2xl mb-4">
            {uploaded ? "Document Processed" : "Upload W-9 / Bank Details"}
          </h3>
          <p className="text-[var(--color-muted)] mb-8 max-w-sm">
            {uploaded 
              ? "The document has been successfully ingested and is ready for agent analysis." 
              : "Drag and drop your PDF or image files here, or click to browse."}
          </p>
          
          <Button 
            variant="primary" 
            className="w-48 relative overflow-hidden"
            onClick={!uploaded && !isUploading ? handleUpload : undefined}
          >
            {isUploading ? "Uploading..." : uploaded ? "Upload Another" : "Select File"}
            {isUploading && (
              <motion.div 
                className="absolute inset-0 bg-white/20"
                initial={{ x: '-100%' }}
                animate={{ x: '100%' }}
                transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
              />
            )}
          </Button>
        </Card>

        {/* Manual Metadata (Optional) */}
        <Card className="p-8">
          <div className="flex items-center gap-4 mb-8">
            <IconWell>
              <FileText className="h-5 w-5" />
            </IconWell>
            <h3 className="font-bold text-xl">Case Metadata</h3>
          </div>
          
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium mb-2 pl-2">Case Type</label>
              <Input defaultValue="Vendor Onboarding" readOnly className="opacity-70" />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2 pl-2">Tenant ID (Optional)</label>
              <Input placeholder="e.g. TENANT-001" />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2 pl-2">Expected Risk Category</label>
              <select className="w-full h-14 bg-transparent border-none rounded-2xl px-6 text-[var(--color-primary)] placeholder-[var(--color-muted)] outline-none shadow-[var(--shadow-inset)] focus:shadow-[var(--shadow-inset-deep)] transition-shadow duration-300 appearance-none">
                <option value="auto">Auto-detect via Agent</option>
                <option value="low">Low Risk (Standard)</option>
                <option value="high">High Risk (International/Software)</option>
              </select>
            </div>
            
            <div className="pt-6 border-t border-[rgba(255,255,255,0.2)]">
              <Button 
                variant="primary" 
                className={`w-full ${!uploaded ? 'opacity-50 cursor-not-allowed' : ''}`}
                disabled={!uploaded}
              >
                Trigger Agentic Pipeline
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
