import React, { useState, useEffect } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";
import { type PropertyId, asPropertyId } from "../types/branded";

interface Property {
  id: string;
  name: string;
}

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[]>([]);
  // selectedProperty is typed PropertyId — not a raw string — so it can only
  // flow into APIs that declare PropertyId as their parameter type.
  const [selectedProperty, setSelectedProperty] = useState<PropertyId | null>(null);

  useEffect(() => {
    SecureAPI.getProperties()
      .then((res) => {
        const list: Property[] = (res.data || []).map((p: Property) => ({
          id: p.id,
          name: p.name,
        }));
        setProperties(list);
        // Cast at the trust boundary: values come from the /properties API
        // response, which the backend has already scoped to this tenant.
        if (list.length > 0) setSelectedProperty(asPropertyId(list[0].id));
      })
      .catch((err) => console.error("Failed to fetch properties:", err));
  }, []);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">
          Property Management Dashboard
        </h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">
                  Revenue Overview
                </h2>
                <p className="text-sm lg:text-base text-gray-600">
                  Monthly performance insights for your properties
                </p>
              </div>

              <div className="flex flex-col sm:items-end">
                <label className="text-xs font-medium text-gray-700 mb-1">
                  Select Property
                </label>
                <select
                  value={selectedProperty ?? ""}
                  onChange={(e) =>
                    setSelectedProperty(
                      e.target.value ? asPropertyId(e.target.value) : null,
                    )
                  }
                  className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  disabled={properties.length === 0}
                >
                  {properties.length === 0 && (
                    <option value="">Loading...</option>
                  )}
                  {properties.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {selectedProperty && (
              <RevenueSummary propertyId={selectedProperty} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
