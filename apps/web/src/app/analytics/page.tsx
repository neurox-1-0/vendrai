"use client";

import React from 'react';
import { Card } from '@/components/ui/card';
import { IconWell } from '@/components/ui/icon-well';
import { Activity, Clock, ShieldCheck, Zap } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { motion } from 'framer-motion';

const processingTimeData = [
  { name: 'Mon', minutes: 12 },
  { name: 'Tue', minutes: 10 },
  { name: 'Wed', minutes: 15 },
  { name: 'Thu', minutes: 8 },
  { name: 'Fri', minutes: 9 },
];

const ocrAccuracyData = [
  { name: 'Mon', accuracy: 92 },
  { name: 'Tue', accuracy: 95 },
  { name: 'Wed', accuracy: 89 },
  { name: 'Thu', accuracy: 98 },
  { name: 'Fri', accuracy: 96 },
];

export default function AnalyticsDashboard() {
  return (
    <div className="p-12 h-full flex flex-col">
      <header className="mb-12">
        <h2 className="font-display font-bold text-3xl mb-2">Agentic Performance Metrics</h2>
        <p className="text-[var(--color-muted)]">Enterprise-level KPIs for the Vendor-to-Pay pipeline.</p>
      </header>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 mb-12">
        {[
          { label: 'Avg Resolution Time', value: '11.2m', icon: Clock, desc: '-45% from manual' },
          { label: 'OCR Confidence', value: '94.5%', icon: ShieldCheck, desc: 'Target: >90%' },
          { label: 'Autonomous Actions', value: '1,248', icon: Zap, desc: 'This week' },
          { label: 'Duplicate Hits', value: '142', icon: Activity, desc: 'Avoided ERP mess' },
        ].map((kpi, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
          >
            <Card className="p-6 h-full flex flex-col justify-center relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <kpi.icon className="w-16 h-16 text-[var(--color-accent)]" />
              </div>
              <p className="text-sm font-bold text-[var(--color-muted)] uppercase tracking-wider mb-2">{kpi.label}</p>
              <p className="font-display font-extrabold text-4xl mb-2">{kpi.value}</p>
              <p className="text-sm text-[var(--color-success)]">{kpi.desc}</p>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 flex-1 min-h-[400px]">
        <Card className="p-8 flex flex-col">
          <h3 className="font-bold text-xl mb-6">Processing Time (Minutes)</h3>
          <div className="flex-1 bg-[var(--color-clay)] rounded-2xl shadow-[var(--shadow-inset-sm)] p-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={processingTimeData} margin={{ top: 20, right: 30, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(0,0,0,0.05)" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: 'var(--color-muted)', fontSize: 12}} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: 'var(--color-muted)', fontSize: 12}} />
                <Tooltip 
                  cursor={{fill: 'rgba(108,99,255,0.05)'}}
                  contentStyle={{ backgroundColor: 'var(--color-clay)', borderRadius: '12px', border: 'none', boxShadow: '5px 5px 10px rgba(163, 177, 198, 0.6), -5px -5px 10px rgba(255, 255, 255, 0.5)' }}
                  itemStyle={{ color: 'var(--color-primary)', fontWeight: 'bold' }}
                />
                <Bar dataKey="minutes" fill="var(--color-accent)" radius={[6, 6, 0, 0]} barSize={40} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-8 flex flex-col">
          <h3 className="font-bold text-xl mb-6">Agent Extraction Accuracy (%)</h3>
          <div className="flex-1 bg-[var(--color-clay)] rounded-2xl shadow-[var(--shadow-inset-sm)] p-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={ocrAccuracyData} margin={{ top: 20, right: 30, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(0,0,0,0.05)" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: 'var(--color-muted)', fontSize: 12}} dy={10} />
                <YAxis domain={[80, 100]} axisLine={false} tickLine={false} tick={{fill: 'var(--color-muted)', fontSize: 12}} />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--color-clay)', borderRadius: '12px', border: 'none', boxShadow: '5px 5px 10px rgba(163, 177, 198, 0.6), -5px -5px 10px rgba(255, 255, 255, 0.5)' }}
                  itemStyle={{ color: 'var(--color-success)', fontWeight: 'bold' }}
                />
                <Line type="monotone" dataKey="accuracy" stroke="var(--color-success)" strokeWidth={4} dot={{ fill: 'var(--color-success)', strokeWidth: 2, r: 4 }} activeDot={{ r: 8 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
    </div>
  );
}
