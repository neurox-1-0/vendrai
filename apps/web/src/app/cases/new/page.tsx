"use client";

import React, { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { IconWell } from '@/components/ui/icon-well';
import { Upload, FileText, CheckCircle2, Info, Building2, Receipt } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function CaseIntake() {
  const [flow, setFlow] = useState<'vendor' | 'invoice'>('vendor');
  const [isUploading, setIsUploading] = useState(false);
  const [uploaded, setUploaded] = useState(false);

  const handleUpload = () => {
    setIsUploading(true);
    setTimeout(() => {
      setIsUploading(false);
      setUploaded(true);
    }, 2000);
  };

  const handleReset = () => {
    setUploaded(false);
    setIsUploading(false);
  };

  return (
    <div className="p-12 h-full flex flex-col">
      <header className="mb-12">
        <h2 className="font-display font-bold text-3xl mb-2">New Case Intake</h2>
        <p className="text-[var(--color-muted)]">Upload evidence to trigger the agentic analysis pipeline.</p>
      </header>

      {/* Flow Selector Toggle */}
      <div className="flex justify-center mb-12">
        <div className="bg-[var(--color-clay)] p-2 rounded-2xl shadow-[var(--shadow-inset)] flex items-center gap-2 w-fit border border-[rgba(255,255,255,0.4)] relative overflow-hidden">
          <motion.div 
            className="absolute top-2 bottom-2 w-[calc(50%-8px)] bg-[var(--color-clay)] rounded-xl shadow-[var(--shadow-extruded)] z-0"
            animate={{ left: flow === 'vendor' ? '8px' : 'calc(50% + 4px)' }}
            transition={{ type: "spring", stiffness: 300, damping: 25 }}
          />
          
          <button 
            onClick={() => { setFlow('vendor'); handleReset(); }}
            className={`relative z-10 px-8 py-3 rounded-xl font-bold flex items-center gap-3 transition-colors ${flow === 'vendor' ? 'text-[var(--color-accent)]' : 'text-[var(--color-muted)] hover:text-[var(--color-primary)]'}`}
          >
            <Building2 className="w-5 h-5" /> Vendor Onboarding
          </button>
          
          <button 
            onClick={() => { setFlow('invoice'); handleReset(); }}
            className={`relative z-10 px-8 py-3 rounded-xl font-bold flex items-center gap-3 transition-colors ${flow === 'invoice' ? 'text-[var(--color-accent)]' : 'text-[var(--color-muted)] hover:text-[var(--color-primary)]'}`}
          >
            <Receipt className="w-5 h-5" /> Invoice Exception
          </button>
        </div>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-12 max-w-7xl mx-auto w-full">
        
        {/* Upload Zone & Metadata */}
        <div className="lg:col-span-2 space-y-12">
          <Card className="flex flex-col items-center justify-center p-16 text-center relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-transparent to-[rgba(108,99,255,0.05)] pointer-events-none" />
            
            <motion.div 
              whileHover={{ scale: 1.05 }}
              className="w-32 h-32 rounded-full shadow-[var(--shadow-extruded)] flex items-center justify-center mb-8 border-4 border-[var(--color-clay)] bg-[var(--color-clay)]"
            >
              {uploaded ? (
                <CheckCircle2 className="h-12 w-12 text-[var(--color-success)]" />
              ) : (
                <Upload className="h-12 w-12 text-[var(--color-accent)] group-hover:-translate-y-2 transition-transform" />
              )}
            </motion.div>
            
            <h3 className="font-bold text-2xl mb-4">
              {uploaded ? "Document Processed" : flow === 'vendor' ? "Upload W-9, Bank Letter, or Contract" : "Upload Exception Invoice"}
            </h3>
            <p className="text-[var(--color-muted)] mb-8 max-w-md mx-auto">
              {uploaded 
                ? "The document has been successfully ingested and is ready for agent analysis." 
                : "Drag and drop your PDF or image files here, or click to browse. The OCR Agent will automatically extract metadata."}
            </p>
            
            <Button 
              variant="primary" 
              className="w-48 relative overflow-hidden h-14"
              onClick={!uploaded && !isUploading ? handleUpload : undefined}
            >
              {isUploading ? "Processing OCR..." : uploaded ? "Upload Additional File" : "Select File"}
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

          <Card className="p-8">
            <div className="flex items-center gap-4 mb-8">
              <IconWell>
                <FileText className="h-5 w-5" />
              </IconWell>
              <h3 className="font-bold text-xl">Case Metadata</h3>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* Dynamic Fields Based on Flow */}
              <AnimatePresence mode="wait">
                {flow === 'vendor' ? (
                  <motion.div 
                    key="vendor-fields"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="contents"
                  >
                    <div>
                      <label className="block text-sm font-medium mb-2 pl-2">Expected Vendor Category</label>
                      <select className="w-full h-14 bg-transparent border-none rounded-2xl px-6 text-[var(--color-primary)] placeholder-[var(--color-muted)] outline-none shadow-[var(--shadow-inset)] focus:shadow-[var(--shadow-inset-deep)] transition-shadow duration-300 appearance-none">
                        <option value="auto">Auto-detect via Agent</option>
                        <option value="software">Software / IT</option>
                        <option value="services">Professional Services</option>
                        <option value="goods">Physical Goods</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2 pl-2">Requester Department</label>
                      <Input placeholder="e.g. Marketing" />
                    </div>
                  </motion.div>
                ) : (
                  <motion.div 
                    key="invoice-fields"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    className="contents"
                  >
                    <div>
                      <label className="block text-sm font-medium mb-2 pl-2">Purchase Order Number</label>
                      <Input placeholder="e.g. PO-2026-9042" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2 pl-2">Exception Type</label>
                      <select className="w-full h-14 bg-transparent border-none rounded-2xl px-6 text-[var(--color-primary)] placeholder-[var(--color-muted)] outline-none shadow-[var(--shadow-inset)] focus:shadow-[var(--shadow-inset-deep)] transition-shadow duration-300 appearance-none">
                        <option value="auto">Auto-detect via Agent</option>
                        <option value="price">Price Variance</option>
                        <option value="quantity">Quantity Mismatch</option>
                        <option value="tax">Tax Discrepancy</option>
                      </select>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            
            <div className="pt-8 mt-8 border-t border-[rgba(255,255,255,0.2)]">
              <Button 
                variant="primary" 
                className={`w-full h-14 text-lg ${!uploaded ? 'opacity-50 cursor-not-allowed' : 'hover:scale-[1.02] transition-transform'}`}
                disabled={!uploaded}
              >
                Trigger {flow === 'vendor' ? 'Onboarding' : 'Exception'} Pipeline
              </Button>
            </div>
          </Card>
        </div>

        {/* Guidelines Side Panel */}
        <div className="space-y-8">
          <Card className="p-8 bg-[var(--color-clay)]">
            <div className="flex items-center gap-3 mb-6">
              <Info className="w-6 h-6 text-[var(--color-accent)]" />
              <h3 className="font-bold text-lg">Agent Guidelines</h3>
            </div>
            
            {flow === 'vendor' ? (
              <div className="space-y-4 text-sm text-[var(--color-muted)]">
                <p>The <strong className="text-[var(--color-primary)]">Document Agent</strong> expects a valid W-9 or Tax Certificate to verify legal identity.</p>
                <p>If banking details are included, the <strong className="text-[var(--color-primary)]">Risk Agent</strong> will cross-reference the bank's country of origin against OFAC sanctions lists.</p>
                <div className="bg-[rgba(108,99,255,0.1)] p-4 rounded-xl border border-[var(--color-accent)] mt-4">
                  <span className="font-bold text-[var(--color-accent)] block mb-1">Tip:</span>
                  Uploading multiple documents (e.g. Tax + Bank Letter) at once improves the confidence score.
                </div>
              </div>
            ) : (
              <div className="space-y-4 text-sm text-[var(--color-muted)]">
                <p>The <strong className="text-[var(--color-primary)]">Reasoning Agent</strong> will compare line items against the provided PO Number via the mocked ERP tool.</p>
                <p>If a price variance exceeds 5%, the <strong className="text-[var(--color-primary)]">Policy Agent</strong> will trigger a mandatory procurement manager approval.</p>
                <div className="bg-[rgba(108,99,255,0.1)] p-4 rounded-xl border border-[var(--color-accent)] mt-4">
                  <span className="font-bold text-[var(--color-accent)] block mb-1">Tip:</span>
                  Ensure the invoice image is clear. The OCR Agent struggles with low-resolution scans.
                </div>
              </div>
            )}
          </Card>
        </div>

      </div>
    </div>
  );
}
