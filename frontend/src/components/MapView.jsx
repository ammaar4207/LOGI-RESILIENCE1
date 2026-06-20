import React, { useEffect, useState, useCallback, useMemo } from 'react';
import DeckGL from '@deck.gl/react';
import { ScatterplotLayer, ArcLayer, TextLayer } from '@deck.gl/layers';
import { Map } from 'react-map-gl';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

import { useStore } from '../store';
import { useRiskStream } from '../hooks/useRiskStream';
import PortDetailsPanel from './PortDetailsPanel';

const INITIAL_VIEW_STATE = {
  longitude: 0,
  latitude: 20,
  zoom: 1.5,
  pitch: 0,
  bearing: 0,
};

// Calculate color gradients for routes
const getRiskColor = (score) => {
  if (score >= 0.7) return [239, 68, 68]; // Red
  if (score >= 0.45) return [245, 158, 11]; // Orange
  return [16, 185, 129]; // Green
};

const MapView = () => {
  const { metrics, meta, activeSimulationPath, mapViewState, setMapViewState, setSelectedPortId } = useStore();
  const livePayload = useRiskStream();
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);

  // Sync state from programmatic zooms
  useEffect(() => {
    if (mapViewState) {
      setViewState(mapViewState);
      // Optional: clear it after transition to allow free panning again
      const timer = setTimeout(() => setMapViewState(null), 1600);
      return () => clearTimeout(timer);
    }
  }, [mapViewState, setMapViewState]);

  useEffect(() => {
    if (livePayload) {
      useStore.getState().setMetrics(livePayload.metrics || []);
      useStore.getState().updateMeta({
        status: livePayload.status,
        updated: new Date(livePayload.timestamp).toLocaleTimeString(),
        nodes: livePayload.network_density?.nodes || 0,
        edges: livePayload.network_density?.edges || 0,
        resilience: livePayload.global_resilience_index,
      });
    }
  }, [livePayload]);

  // Derive unique ports from the lane metrics for the ScatterplotLayer
  const ports = useMemo(() => {
    const portMap = new Map();
    metrics.forEach(lane => {
      if (lane.source_id && lane.source_coords) {
        if (!portMap.has(lane.source_id)) portMap.set(lane.source_id, { id: lane.source_id, coords: lane.source_coords });
      }
      if (lane.target_id && lane.target_coords) {
        if (!portMap.has(lane.target_id)) portMap.set(lane.target_id, { id: lane.target_id, coords: lane.target_coords });
      }
    });
    return Array.from(portMap.values());
  }, [metrics]);

  const layers = [
    // ── Shipping Lanes (ArcLayer) ───────────────────────────────────────────
    new ArcLayer({
      id: 'shipping-lanes',
      data: metrics,
      getSourcePosition: d => d.source_coords || [0, 0],
      getTargetPosition: d => d.target_coords || [0, 0],
      getSourceColor: d => getRiskColor(d.risk_score),
      getTargetColor: d => getRiskColor(d.risk_score),
      getWidth: d => (d.risk_score >= 0.7 ? 4 : 2),
      pickable: true,
      autoHighlight: true,
      highlightColor: [56, 189, 248, 200],
    }),

    // ── Simulated Optimal Route (ArcLayer) ──────────────────────────────────
    ...(activeSimulationPath ? [
      new ArcLayer({
        id: 'simulation-path',
        data: (() => {
          const pathEdges = [];
          for (let i = 0; i < activeSimulationPath.path.length - 1; i++) {
            const srcId = activeSimulationPath.path[i];
            const tgtId = activeSimulationPath.path[i + 1];
            const srcPort = ports.find(p => p.id === srcId);
            const tgtPort = ports.find(p => p.id === tgtId);
            if (srcPort && tgtPort) {
              pathEdges.push({ source: srcPort.coords, target: tgtPort.coords });
            }
          }
          return pathEdges;
        })(),
        getSourcePosition: d => d.source,
        getTargetPosition: d => d.target,
        getSourceColor: [56, 189, 248], // Brand blue
        getTargetColor: [99, 102, 241], // Brand indigo
        getWidth: 8,
      })
    ] : []),

    // ── Port Terminals (ScatterplotLayer) ───────────────────────────────────
    new ScatterplotLayer({
      id: 'ports-layer',
      data: ports,
      getPosition: d => d.coords,
      getFillColor: [15, 23, 42],
      getLineColor: [56, 189, 248],
      getLineWidth: 2,
      getRadius: viewState.zoom < 3 ? 40000 : 20000,
      pickable: true,
      onClick: ({ object }) => {
        if (object) {
          setSelectedPortId(object.id);
          setViewState({
            ...viewState,
            longitude: object.coords[0],
            latitude: object.coords[1],
            zoom: Math.max(viewState.zoom, 5),
            transitionDuration: 1000,
          });
        }
      }
    }),

    // ── Port Labels (TextLayer) ─────────────────────────────────────────────
    new TextLayer({
      id: 'port-labels',
      data: ports,
      getPosition: d => d.coords,
      getText: d => d.id,
      getSize: 12,
      getColor: [255, 255, 255, 200],
      getAlignmentBaseline: 'bottom',
      getPixelOffset: [0, -10],
      fontFamily: 'Inter',
      fontWeight: 'bold',
      visible: viewState.zoom > 3, // Only show text when zoomed in
    }),
  ];

  return (
    <div className="map-viewport">
      <DeckGL
        layers={layers}
        viewState={viewState}
        onViewStateChange={({ viewState }) => setViewState(viewState)}
        controller={{ minZoom: 0, maxZoom: 20, dragRotate: true }}
        getTooltip={({ object }) => {
          if (!object) return null;
          if (object.risk_score !== undefined) {
            return `${object.name}\nRisk: ${Math.round(object.risk_score * 100)}%`;
          }
          if (object.id) {
            return `Terminal: ${object.id}\nClick for details`;
          }
          return null;
        }}
      >
        <Map
          mapLib={maplibregl}
          mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
          reuseMaps
        />
      </DeckGL>
      
      {/* Port Details Floating Panel */}
      <PortDetailsPanel />

      {/* Legend Overlay */}
      <div className="map-legend-overlay">
        <h4 style={{ margin: '0 0 10px 0', fontSize: 12, color: 'var(--text-primary)', letterSpacing: 1 }}>NETWORK STATUS</h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 11, color: 'var(--text-secondary)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 12, height: 4, background: 'var(--status-ok)', borderRadius: 2 }} /> Stable (Risk &lt; 45%)
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 12, height: 4, background: 'var(--status-warn)', borderRadius: 2 }} /> Degraded (Risk 45-70%)
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 12, height: 4, background: 'var(--status-crit)', borderRadius: 2 }} /> Critical (Risk &ge; 70%)
          </div>
          {activeSimulationPath && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
              <span style={{ width: 12, height: 4, background: 'linear-gradient(90deg, var(--brand-blue), var(--brand-indigo))', borderRadius: 2 }} /> Optimal Reroute
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MapView;