import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';
import { type PropertyId } from '../types/branded';

interface RevenueData {
    property_id: string;
    total_revenue: string;
    currency: string;
    reservations_count: number;
}

interface RevenueSummaryProps {
    // PropertyId (branded) — cannot pass a raw string without an explicit asPropertyId() cast.
    propertyId?: PropertyId;
    debugTenant?: string;
    showRaw?: boolean;
}

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId, debugTenant, showRaw }) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [retryCount, setRetryCount] = useState(0);

    const activeTenant = import.meta.env.DEV ? (debugTenant || undefined) : undefined;

    useEffect(() => {
        if (!propertyId) {
            setLoading(false);
            setData(null);
            return;
        }
        const fetchRevenue = async () => {
            setLoading(true);
            setError('');
            try {
                const response = await SecureAPI.getDashboardSummary(propertyId, {
                    ...(activeTenant ? { simulatedTenant: activeTenant } : {}),
                });
                setData(response);
            } catch (err) {
                setError('Failed to load revenue data');
                console.error(err);
            } finally {
                setLoading(false);
            }
        };

        fetchRevenue();
    }, [propertyId, activeTenant, retryCount]);

    if (loading) {
        return (
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <div className="animate-pulse space-y-4">
                    <div className="h-4 bg-gray-100 rounded w-1/4"></div>
                    <div className="h-8 bg-gray-100 rounded w-1/2"></div>
                    <div className="flex gap-4 pt-4">
                        <div className="h-12 bg-gray-100 rounded flex-1"></div>
                        <div className="h-12 bg-gray-100 rounded flex-1"></div>
                    </div>
                </div>
            </div>
        );
    }

    if (error) return (
        <div className="bg-white rounded-xl shadow-sm border border-red-200 p-6">
            <div className="flex items-start gap-3">
                <svg className="h-5 w-5 text-red-400 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div className="flex-1">
                    <p className="text-sm font-medium text-red-800">Revenue data unavailable</p>
                    <p className="text-xs text-red-600 mt-0.5">Could not load revenue for this property.</p>
                    <button
                        onClick={() => setRetryCount(c => c + 1)}
                        className="mt-3 text-xs font-medium text-red-700 underline hover:text-red-900 focus:outline-none"
                    >
                        Try again
                    </button>
                </div>
            </div>
        </div>
    );
    if (!data) return null;

    const parsed = Number.parseFloat(data.total_revenue);
    const rounded = Math.round(parsed * 100) / 100;
    const displayTotal = new Intl.NumberFormat(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(rounded);

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-300">
            {showRaw && (
                <div className="p-3 bg-gray-50 text-xs font-mono border-b border-gray-100 overflow-auto max-h-32">
                    <strong className="block mb-1 text-gray-500 uppercase tracking-wider text-[10px]">Raw API Response</strong>
                    <pre className="text-gray-700">{JSON.stringify(data, null, 2)}</pre>
                </div>
            )}

            <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Total Revenue</h2>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-3xl font-bold text-gray-900 tracking-tight">
                                {data.currency} {displayTotal}
                            </span>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Property ID</p>
                        <p className="text-sm font-semibold text-gray-700 font-mono mt-1">{data.property_id}</p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Reservations</p>
                        <p className="text-sm font-semibold text-gray-700 mt-1">{data.reservations_count} <span className="font-normal text-gray-400">bookings</span></p>
                    </div>
                </div>

                {/* Precision Warning Area */}
                <div className="mt-4 h-6">
                    {Math.abs(parsed - rounded) > 0.000001 && (
                        <div className="flex items-center text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded">
                            <svg className="h-4 w-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            Precision Mismatch Detected
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
