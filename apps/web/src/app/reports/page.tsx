"use client";

import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { IconWell } from '@/components/ui/icon-well';
import { FileText, Download, Calendar, Filter } from 'lucide-react';
import { motion } from 'framer-motion';

export default function ReportsPage() {
  const reports = [
    { name: "Monthly Compliance Audit", date: "Oct 1, 2026", type: "PDF", size: "2.4 MB" },
    { name: "Vendor Risk Assessment (Q3)", date: "Sep 28, 2026", type: "CSV", size: "845 KB" },
    { name: "Invoice Exceptions Log", date: "Sep 25, 2026", type: "Excel", size: "1.2 MB" },
    { name: "Agent Trace History", date: "Sep 20, 2026", type: "JSON", size: "4.8 MB" },
  ];

  return (
    <div className="p-12 h-full flex flex-col">
      <header className="mb-12 flex justify-between items-end">
        <div>
          <h2 className="font-display font-bold text-3xl mb-2">Export Reports</h2>
          <p className="text-[var(--color-muted)]">Download historical agent data and compliance logs.</p>
        </div>
        
        <div className="flex gap-4">
          <Button variant="secondary" className="gap-2">
            <Filter className="w-4 h-4" /> Filter
          </Button>
          <Button variant="secondary" className="gap-2">
            <Calendar className="w-4 h-4" /> Date Range
          </Button>
        </div>
      </header>

      <Card className="flex-1 overflow-hidden flex flex-col p-8">
        <div className="grid grid-cols-12 gap-4 pb-4 border-b border-[rgba(255,255,255,0.1)] text-sm font-bold text-[var(--color-muted)] px-4">
          <div className="col-span-6">Report Name</div>
          <div className="col-span-2">Date Generated</div>
          <div className="col-span-2">Format</div>
          <div className="col-span-2 text-right">Action</div>
        </div>
        
        <div className="flex-1 overflow-y-auto space-y-2 mt-4 pr-2">
          {reports.map((report, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
              className="grid grid-cols-12 gap-4 items-center p-4 rounded-xl hover:bg-[var(--color-clay)] hover:shadow-[var(--shadow-inset-sm)] transition-all group"
            >
              <div className="col-span-6 flex items-center gap-4">
                <IconWell className="shrink-0 bg-transparent shadow-none border border-[rgba(255,255,255,0.2)] group-hover:border-[var(--color-accent)] transition-colors">
                  <FileText className="w-5 h-5 text-[var(--color-primary)] group-hover:text-[var(--color-accent)]" />
                </IconWell>
                <span className="font-bold">{report.name}</span>
              </div>
              <div className="col-span-2 text-sm text-[var(--color-muted)]">{report.date}</div>
              <div className="col-span-2">
                <span className="text-xs font-bold px-3 py-1 bg-[rgba(255,255,255,0.05)] rounded-full border border-[rgba(255,255,255,0.1)]">
                  {report.type}
                </span>
              </div>
              <div className="col-span-2 flex justify-end">
                <button className="w-10 h-10 flex items-center justify-center rounded-full bg-[var(--color-bg)] shadow-[var(--shadow-extruded-sm)] hover:bg-[var(--color-accent)] transition-all group/btn border border-[rgba(255,255,255,0.3)]">
                  <Download className="w-5 h-5 text-[var(--color-primary)] group-hover/btn:text-white" strokeWidth={2} />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      </Card>
    </div>
  );
}
