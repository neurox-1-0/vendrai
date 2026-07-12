"use client";

import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ShieldCheck, AlertTriangle, Search, Filter, MoreVertical, ArrowRight } from 'lucide-react';
import { motion } from 'framer-motion';
import Link from 'next/link';

export default function ApprovalsDashboard() {
  const cases = [
    {
      id: 'CASE-8492',
      vendor: 'Vendrai Technologies LLC',
      status: 'REQUIRES_REVIEW',
      risk: 'HIGH',
      flag: 'OFAC Sanctions Potential Match',
      date: '2 mins ago'
    },
    {
      id: 'CASE-8491',
      vendor: 'Acme Supplies Inc',
      status: 'PENDING_APPROVAL',
      risk: 'MEDIUM',
      flag: 'Missing Bank Swift Code',
      date: '1 hour ago'
    },
    {
      id: 'CASE-8490',
      vendor: 'Global Consulting LLC',
      status: 'REQUIRES_REVIEW',
      risk: 'HIGH',
      flag: 'Policy Violation (PROC-405)',
      date: '3 hours ago'
    }
  ];

  return (
    <div className="p-12 h-full flex flex-col">
      <header className="mb-12 flex justify-between items-end">
        <div>
          <h2 className="font-display font-bold text-3xl mb-2">Human Approval Queue</h2>
          <p className="text-[var(--color-muted)]">Cases requiring manual intervention or policy exceptions.</p>
        </div>
        <div className="flex gap-4">
          <Button variant="secondary" className="gap-2"><Filter className="w-4 h-4" /> Filter</Button>
          <Button variant="secondary" className="gap-2"><Search className="w-4 h-4" /> Search</Button>
        </div>
      </header>

      <div className="flex-1 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 content-start">
        {cases.map((c, i) => (
          <motion.div
            key={c.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
          >
            <Card className="p-8 flex flex-col h-full group relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-[var(--color-accent)]" />
              
              <div className="flex justify-between items-start mb-6">
                <span className="text-sm font-bold text-[var(--color-muted)]">{c.id}</span>
                <Button variant="icon" className="w-8 h-8 opacity-50 hover:opacity-100">
                  <MoreVertical className="w-4 h-4" />
                </Button>
              </div>
              
              <h3 className="font-display font-bold text-xl mb-2">{c.vendor}</h3>
              
              <div className="flex items-center gap-2 mb-6">
                <AlertTriangle className={`w-4 h-4 ${c.risk === 'HIGH' ? 'text-red-500' : 'text-yellow-500'}`} />
                <span className={`text-sm font-bold ${c.risk === 'HIGH' ? 'text-red-500' : 'text-yellow-500'}`}>
                  {c.risk} RISK
                </span>
                <span className="text-[var(--color-muted)] text-sm">• {c.date}</span>
              </div>
              
              <div className="flex-1">
                <div className="bg-[var(--color-clay)] rounded-xl p-4 shadow-[var(--shadow-inset-sm)] mb-8">
                  <span className="text-sm font-bold text-[var(--color-primary)] block mb-1">Flagged Reason:</span>
                  <span className="text-sm text-[var(--color-muted)]">{c.flag}</span>
                </div>
              </div>
              
              <Link href={`/cases/${c.id}`} className="block w-full">
                <Button variant="primary" className="w-full justify-center gap-2 group-hover:scale-105 transition-transform">
                  Review Case <ArrowRight className="w-4 h-4" />
                </Button>
              </Link>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
