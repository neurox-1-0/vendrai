"use client";

import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { IconWell } from '@/components/ui/icon-well';
import { FileText, Copy, AlertTriangle, ShieldAlert, CheckCircle2, Bot, ArrowLeft } from 'lucide-react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useParams } from 'next/navigation';

export default function CaseAuditTrace() {
  const params = useParams();
  const caseId = params.id as string;

  const traceSteps = [
    {
      agent: 'Document Extraction',
      status: 'success',
      icon: FileText,
      detail: "Extracted Vendor: Vendrai Technologies LLC. Tax ID: 98-7654321."
    },
    {
      agent: 'Duplicate Detection',
      status: 'warning',
      icon: Copy,
      detail: "Exact match found in ERP (ID: ERP-1001) based on Tax ID. Confidence: 100%."
    },
    {
      agent: 'Risk Assessment',
      status: 'danger',
      icon: AlertTriangle,
      detail: "Sanctions hit detected on vendor name. Risk Level set to HIGH."
    },
    {
      agent: 'Policy Retrieval',
      status: 'danger',
      icon: ShieldAlert,
      detail: "Violation of PROC-405. High-risk vendors require explicit CFO sign-off."
    }
  ];

  return (
    <div className="p-12 h-full flex flex-col">
      <header className="mb-12 flex justify-between items-center">
        <div className="flex items-center gap-6">
          <Link href="/approvals">
            <Button variant="icon" className="w-12 h-12">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
          <div>
            <h2 className="font-display font-bold text-3xl mb-1">{caseId}</h2>
            <p className="text-[var(--color-muted)]">Vendrai Technologies LLC • Submitted 2 mins ago</p>
          </div>
        </div>
        
        <div className="flex gap-4">
          <Button variant="secondary" className="text-red-500 hover:text-red-600">Reject Vendor</Button>
          <Button variant="primary">Override & Approve</Button>
        </div>
      </header>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-12">
        {/* LangGraph Trace Timeline */}
        <Card className="lg:col-span-2 p-12">
          <h3 className="font-bold text-2xl mb-8 flex items-center gap-3">
            <Bot className="w-6 h-6 text-[var(--color-accent)]" /> Agentic Audit Trace
          </h3>
          
          <div className="space-y-8 relative before:absolute before:inset-0 before:ml-6 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-[var(--color-accent)] before:to-transparent">
            
            {traceSteps.map((step, index) => (
              <motion.div 
                key={index}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.2 }}
                className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active"
              >
                <div className="flex items-center justify-center w-12 h-12 rounded-full border-4 border-[var(--color-clay)] bg-[var(--color-clay)] shadow-[var(--shadow-extruded)] text-slate-500 group-[.is-active]:text-[var(--color-accent)] shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10">
                  <step.icon className="w-5 h-5" />
                </div>
                
                <div className="w-[calc(100%-4rem)] md:w-[calc(50%-3rem)] p-6 rounded-2xl shadow-[var(--shadow-inset-sm)] bg-[var(--color-clay)]">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-bold text-lg">{step.agent}</h4>
                    {step.status === 'success' && <CheckCircle2 className="w-5 h-5 text-[var(--color-success)]" />}
                    {step.status === 'warning' && <AlertTriangle className="w-5 h-5 text-yellow-500" />}
                    {step.status === 'danger' && <ShieldAlert className="w-5 h-5 text-red-500" />}
                  </div>
                  <p className="text-[var(--color-muted)] text-sm">{step.detail}</p>
                </div>
              </motion.div>
            ))}

          </div>
        </Card>

        {/* Extracted Data Panel */}
        <div className="space-y-8">
          <Card className="p-8">
            <h3 className="font-bold text-xl mb-6">Extracted Metadata</h3>
            
            <div className="space-y-4">
              <div className="bg-[var(--color-clay)] rounded-xl p-4 shadow-[var(--shadow-inset-sm)]">
                <span className="text-xs font-bold text-[var(--color-muted)] uppercase tracking-wider block mb-1">Legal Name</span>
                <span className="font-medium">Vendrai Technologies LLC</span>
              </div>
              <div className="bg-[var(--color-clay)] rounded-xl p-4 shadow-[var(--shadow-inset-sm)]">
                <span className="text-xs font-bold text-[var(--color-muted)] uppercase tracking-wider block mb-1">Tax ID</span>
                <span className="font-medium">98-7654321</span>
              </div>
              <div className="bg-[var(--color-clay)] rounded-xl p-4 shadow-[var(--shadow-inset-sm)]">
                <span className="text-xs font-bold text-[var(--color-muted)] uppercase tracking-wider block mb-1">Address</span>
                <span className="font-medium text-sm">123 Innovation Drive, Suite 400, San Francisco, CA 94105</span>
              </div>
            </div>
          </Card>
          
          <Card className="p-8 border-2 border-red-500/20">
            <h3 className="font-bold text-xl mb-4 text-red-500">Required Actions</h3>
            <p className="text-sm text-[var(--color-muted)] mb-6">
              The Policy Agent determined this case requires manual override due to a HIGH risk OFAC sanction match on the vendor name.
            </p>
            <div className="bg-red-500/10 rounded-xl p-4 border border-red-500/20 text-red-700 font-medium text-sm">
              PROC-405: CFO and CCO Sign-off Required
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
