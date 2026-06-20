import React, { useMemo } from 'react';
import DeckGL from '@deck.gl/react';
import { AmbientLight, PointLight, LightingEffect } from '@deck.gl/core';
import { ArcLayer, ColumnLayer, ScatterplotLayer, IconLayer } from '@deck.gl/layers';
import { TripsLayer } from '@deck.gl/geo-layers';
import { geoInterpolate } from 'd3-geo';
import { Map as ReactMapGL } from 'react-map-gl/maplibre';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useStore } from '../store';
import PortDetailsPanel from './PortDetailsPanel';

const SHIP_ICON_MAPPING = {
  marker: { x: 0, y: 0, width: 128, height: 128, mask: true }
};

const haversineDistance = (lon1, lat1, lon2, lat2) => {
  const R = 6371; // km
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
};

const SHIP_ICON_URL = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128"><polygon points="64,10 100,110 64,90 28,110" fill="white"/></svg>';

const ambientLight = new AmbientLight({
  color: [255, 255, 255],
  intensity: 0.6
});
const pointLight = new PointLight({
  color: [255, 255, 255],
  intensity: 2.0,
  position: [0, 20, 8000000]
});
const lightingEffect = new LightingEffect({ ambientLight, pointLight });

const INITIAL_VIEW_STATE = {
  longitude: 0,
  latitude: 20,
  zoom: 1.5,
  minZoom: 0.5,
  pitch: 50,
  bearing: 0
};

export default function Map3D({ metrics, optimizationMode }) {
  const { disruptions, activeSimulationPath, mapViewState, setMapViewState, setSelectedPortId, aisShips, forecastDays, camps } = useStore();
  const [viewState, setViewState] = React.useState(INITIAL_VIEW_STATE);
  const [time, setTime] = React.useState(0);
  const LOOP_LENGTH = 10000;
  const ANIMATION_SPEED = 20;

  React.useEffect(() => {
    let animationFrame;
    const animate = () => {
      setTime(t => (t + ANIMATION_SPEED) % LOOP_LENGTH);
      animationFrame = window.requestAnimationFrame(animate);
    };
    animate();
    return () => window.cancelAnimationFrame(animationFrame);
  }, []);

  // Sync state from programmatic zooms
  React.useEffect(() => {
    if (mapViewState) {
      setViewState(mapViewState);
      const timer = setTimeout(() => setMapViewState(null), 1600);
      return () => clearTimeout(timer);
    }
  }, [mapViewState, setMapViewState]);

  const trips = useMemo(() => {
    if (!metrics) return [];
    const tripsData = [];

    metrics.forEach(m => {
      if (m.is_detoured) return;

      let [sLon, sLat] = m.source_coords;
      let [tLon, tLat] = m.target_coords;

      const interpolate = geoInterpolate([sLon, sLat], [tLon, tLat]);
      const numSegments = 50;
      const path = [];
      const timestamps = [];

      let prevLon = sLon;
      for (let i = 0; i <= numSegments; i++) {
        const [lon, lat] = interpolate(i / numSegments);
        let unwrappedLon = lon;
        if (unwrappedLon - prevLon > 180) unwrappedLon -= 360;
        else if (prevLon - unwrappedLon > 180) unwrappedLon += 360;

        path.push([unwrappedLon, lat]);
        timestamps.push((i / numSegments) * LOOP_LENGTH);
        prevLon = unwrappedLon;
      }

      // Generate a dense fleet (roughly ~50 to 150 vessels per active lane)
      const numVessels = Math.max(10, Math.floor((m.lane_activity || 50) * 1.5));
      const isCritical = m.risk_score > 0.7;

      for (let v = 0; v < numVessels; v++) {
        const delay = (LOOP_LENGTH / numVessels) * v;
        const vesselTimestamps = timestamps.map(t => {
          if (isCritical) return t * 1000 + delay; // Vessels are completely trapped in critical storm/choke zones
          return t + delay;
        });

        tripsData.push({
          path,
          timestamps: vesselTimestamps,
          color: isCritical ? [239, 68, 68, 255] : [16, 185, 129, 255],
          isCritical
        });
      }
    });
    return tripsData;
  }, [metrics]);

  // Calculate predicted ship positions if forecastDays > 0
  const predictedAisShips = useMemo(() => {
    if (!aisShips) return [];
    if (forecastDays === 0 || !metrics) return aisShips;

    return aisShips.map(ship => {
      // Find the lane for this ship
      const lane = metrics.find(m => m.target_id === ship.destination);
      if (!lane) return ship; // Cannot predict if lane is unknown

      // Speed in km/h
      const speedKmh = (ship.speed || 20) * 1.852;

      // Apply disruption logic to speed
      let speedMultiplier = 1.0;
      if (lane.status === 'CRITICAL') speedMultiplier = 0.1; // Stalled/trapped
      else if (lane.status === 'DEGRADED') speedMultiplier = 0.5; // Slowed due to congestion/weather

      const distanceTraveledKm = speedKmh * speedMultiplier * 24 * forecastDays;
      
      let [sLon, sLat] = lane.source_coords;
      let [tLon, tLat] = lane.target_coords;

      // Fix antimeridian crossing for interpolation
      if (sLon - tLon > 180) tLon += 360;
      else if (tLon - sLon > 180) sLon += 360;

      const totalDistKm = lane.carbon_metrics?.distance_km || 5000;
      const currentDistFromSrc = haversineDistance(sLon, sLat, ship.lon, ship.lat);
      let progress = (currentDistFromSrc + distanceTraveledKm) / totalDistKm;

      // Bouncing logic if ship reaches destination
      let isReturning = false;
      if (progress > 1.0) {
        const trips = Math.floor(progress);
        progress = progress - trips;
        if (trips % 2 === 1) {
          isReturning = true;
          progress = 1.0 - progress; // going backwards
        }
      }

      const interpolate = geoInterpolate([sLon, sLat], [tLon, tLat]);
      const newCoords = interpolate(progress);
      let newLon = newCoords[0];
      if (newLon > 180) newLon -= 360;
      else if (newLon < -180) newLon += 360;

      let newHeading = ship.heading;
      if (isReturning) {
        newHeading = (newHeading + 180) % 360;
      }

      return {
        ...ship,
        lat: newCoords[1],
        lon: newLon,
        heading: newHeading,
        speed: ship.speed * speedMultiplier // Show reduced speed in tooltip
      };
    });
  }, [aisShips, forecastDays, metrics]);

  const layers = useMemo(() => {
    if (!metrics) return [];

    // Nodes / Ports - deduplicate by id
    const rawNodes = metrics.flatMap(m => [
      { id: m.source_id, coordinates: m.source_coords },
      { id: m.target_id, coordinates: m.target_coords }
    ]);
    const nodes = Array.from(new Map(rawNodes.map(n => [n.id, n])).values());

    const isEdgeInPath = (d) => {
      if (!activeSimulationPath || !activeSimulationPath.lanes) return false;
      return activeSimulationPath.lanes.includes(d.id);
    };

    const getEdgeColor = (d) => {
      if (isEdgeInPath(d)) return [129, 140, 248, 255]; // Indigo/Brand color for the optimal route

      if (optimizationMode === 'sustainability') {
        const co2 = d.carbon_metrics?.co2_per_teu || 200;
        if (co2 > 300) return [244, 63, 94, 255]; // Rose (Heavy)
        if (co2 >= 200) return [168, 85, 247, 255]; // Purple (Standard)
        return [16, 185, 129, 255]; // Green (Eco)
      } else if (optimizationMode === 'essential') {
        if (d.is_detoured) return [56, 189, 248, 255]; // Sky Blue for Reroutes
        const priority = d.essential_priority || 0.5;
        if (priority >= 0.7) return [250, 204, 21, 255]; // Gold/Yellow (High Priority)
        if (priority >= 0.4) return [148, 163, 184, 255]; // Silver/Slate (Normal Priority)
        return [51, 65, 85, 255]; // Dark Slate (Low Priority)
      } else if (optimizationMode === 'financial') {
        const rate = d.current_spot_rate || 1500;
        if (rate >= 2500) return [239, 68, 68, 255]; // Red (Expensive)
        if (rate >= 1000) return [245, 158, 11, 255]; // Orange (Moderate)
        return [16, 185, 129, 255]; // Green (Cheap)
      } else {
        const risk = d.risk_score || 0;
        if (risk > 0.7) return [239, 68, 68, 255]; // Red (Critical)
        if (risk >= 0.45) return [245, 158, 11, 255]; // Orange (Moderate)
        return [6, 182, 212, 255]; // Cyan (Stable)
      }
    };

    const getEdgeWidth = (d) => {
      if (isEdgeInPath(d)) return 8; // Highlighted path is thicker

      if (optimizationMode === 'sustainability') {
        return d.carbon_metrics?.co2_per_teu > 300 ? 5 : 2;
      } else if (optimizationMode === 'essential') {
        const priority = d.essential_priority || 0.5;
        return priority >= 0.7 ? 6 : (priority >= 0.4 ? 3 : 1);
      } else if (optimizationMode === 'financial') {
        const rate = d.current_spot_rate || 1500;
        return rate >= 2500 ? 5 : 2;
      }
      return d.risk_score > 0.7 ? 5 : 2;
    };

    const adjustedMetrics = metrics.map(m => {
      let [sLon, sLat] = m.source_coords;
      let [tLon, tLat] = m.target_coords;

      // Fix antimeridian crossing (Date Line)
      if (sLon - tLon > 180) {
        tLon += 360;
      } else if (tLon - sLon > 180) {
        sLon += 360;
      }

      return {
        ...m,
        adj_source_coords: [sLon, sLat],
        adj_target_coords: [tLon, tLat]
      };
    });

    return [
      new ColumnLayer({
        id: 'ports',
        data: nodes,
        diskResolution: 6, // hexagon pillars
        radius: 40000, // 40km radius
        extruded: true,
        pickable: true,
        elevationScale: 5000,
        getPosition: d => d.coordinates,
        getFillColor: [6, 182, 212, 255], // Cyber cyan
        getElevation: d => (d.id.length * 40) + 100, // Massive height boost so they punch into the sky
        material: {
          ambient: 0.5,
          diffuse: 0.8,
          shininess: 32,
          specularColor: [255, 255, 255]
        },
        onClick: ({ object }) => {
          if (object) {
            setSelectedPortId(object.id);
            setViewState({
              ...viewState,
              longitude: object.coordinates[0],
              latitude: object.coordinates[1],
              zoom: Math.max(viewState.zoom, 5),
              transitionDuration: 1000,
            });
          }
        }
      }),
      new ArcLayer({
        id: 'shipping-lanes',
        data: adjustedMetrics,
        getSourcePosition: d => d.adj_source_coords,
        getTargetPosition: d => d.adj_target_coords,
        getSourceColor: getEdgeColor,
        getTargetColor: getEdgeColor,
        getWidth: getEdgeWidth,
        widthMinPixels: 2,
        getHeight: 0.15, // Increase arc height multiplier for dramatic 3D curves
        greatCircle: false, // Set to false to avoid clipping across wrapped coordinates
        numSegments: 80, // High segment count for smooth paths
        pickable: true,
        updateTriggers: {
          getSourceColor: [activeSimulationPath, optimizationMode],
          getTargetColor: [activeSimulationPath, optimizationMode],
          getWidth: [activeSimulationPath, optimizationMode]
        }
      }),
      new ScatterplotLayer({
        id: 'disruption-rings',
        data: disruptions.filter(d => d.lat !== null && d.lon !== null && (d.severity === undefined || d.severity > 0.05)),
        getPosition: d => [d.lon, d.lat],
        getFillColor: d => {
          const sev = d.severity !== undefined ? d.severity : 1.0;
          return [244, 63, 94, Math.floor(255 * 0.3 * sev)];
        },
        getLineColor: d => {
          const sev = d.severity !== undefined ? d.severity : 1.0;
          return [244, 63, 94, Math.floor(255 * sev)];
        },
        getLineWidth: 4000,
        lineWidthUnits: 'meters',
        getRadius: d => {
          const sev = d.severity !== undefined ? d.severity : 1.0;
          const baseRadius = d.radius_km > 0 ? d.radius_km * 1000 : 80000;
          return baseRadius * (0.2 + (sev * 0.8));
        },
        radiusMinPixels: 10,
        stroked: true,
        filled: true,
        pickable: true,
        updateTriggers: {
          getRadius: [disruptions],
          getFillColor: [disruptions],
          getLineColor: [disruptions]
        }
      }),
      new TripsLayer({
        id: 'vessels',
        data: trips,
        getPath: d => d.path,
        getTimestamps: d => d.timestamps,
        getColor: d => d.color,
        opacity: 0.9,
        widthMinPixels: 3,
        trailLength: 200,
        currentTime: time,
      }),
      new IconLayer({
        id: 'ais-ships',
        data: predictedAisShips,
        iconAtlas: SHIP_ICON_URL,
        iconMapping: SHIP_ICON_MAPPING,
        getIcon: d => 'marker',
        sizeScale: 12,
        getPosition: d => [d.lon, d.lat],
        getAngle: d => -(d.heading || 0),
        getColor: [250, 204, 21, 255], // High-visibility Gold for AIS Ships
        updateTriggers: {
          getPosition: [predictedAisShips],
          getAngle: [predictedAisShips]
        },
        billboard: false,
        pickable: true
      }),
      new ScatterplotLayer({
        id: 'ngo-camps',
        data: camps || [],
        getPosition: d => [d.lon, d.lat],
        getFillColor: d => {
          if (d.current_days_supply <= 3) return [239, 68, 68, 255]; // Red for Critical
          if (d.current_days_supply < 7) return [245, 158, 11, 255]; // Orange for Warning
          return [16, 185, 129, 255]; // Green for Healthy
        },
        getLineColor: [255, 255, 255, 255],
        getLineWidth: 2000,
        lineWidthUnits: 'meters',
        getRadius: d => {
          const popFactor = Math.log10(d.population) * 15000;
          return d.current_days_supply <= 3 ? popFactor * 1.5 : popFactor;
        },
        radiusMinPixels: 6,
        stroked: true,
        filled: true,
        pickable: true,
        updateTriggers: {
          getFillColor: [camps],
          getRadius: [camps]
        }
      })
    ];
  }, [metrics, optimizationMode, disruptions, activeSimulationPath, trips, time, predictedAisShips, camps]);

  return (
    <div className="relative w-full h-full">
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState }) => setViewState(viewState)}
        controller={{ minZoom: 0, maxZoom: 20, dragRotate: true }}
        layers={layers}
        effects={[lightingEffect]}
        wrapLongitude={true}
        getTooltip={({ object }) => {
          if (!object) return null;
          if (object.mmsi) {
            return {
              html: `
                <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 4px; border-bottom: 1px solid #334155; padding-bottom: 4px; display: flex; justify-content: space-between; gap: 16px;">
                  <span>🚢 ${object.vessel_name}</span>
                  <span style="font-size: 10px; color: #64748b;">MMSI: ${object.mmsi}</span>
                </div>
                <div style="font-size: 11px; color: #cbd5e1; margin-top: 8px; display: flex; justify-content: space-between;">
                  <span>Status:</span> <span style="color: ${object.status === 'underway' ? '#10b981' : '#f59e0b'}; text-transform: uppercase;">${object.status}</span>
                </div>
                <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px; display: flex; justify-content: space-between;">
                  <span>Speed:</span> <span style="font-family: monospace;">${(object.speed || 0).toFixed(1)} knots</span>
                </div>
                <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px; display: flex; justify-content: space-between;">
                  <span>Destination:</span> <span>${object.destination}</span>
                </div>
                <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px; display: flex; justify-content: space-between;">
                  <span>Cargo:</span> <span style="text-transform: capitalize;">${object.cargo_type}</span>
                </div>
              `,
              style: {
                backgroundColor: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(12px)',
                border: '1px solid #ec4899',
                borderRadius: '8px',
                padding: '12px',
                boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)'
              }
            };
          }
          if (object.id && !object.source_id) {
            // It could be a port or a disruption ring
            if (object.type && object.target) {
              return {
                html: `
                  <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 4px; border-bottom: 1px solid #334155; padding-bottom: 4px;">Disruption: ${object.type.toUpperCase()}</div>
                  <div style="font-size: 11px; color: #94a3b8;">Target: ${object.target}</div>
                `,
                style: {
                  backgroundColor: 'rgba(15, 23, 42, 0.85)',
                  backdropFilter: 'blur(12px)',
                  border: '1px solid #334155',
                  borderRadius: '8px',
                  padding: '12px',
                  boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)'
                }
              };
            }
            if (object.population) {
              return {
                html: `
                  <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 4px; border-bottom: 1px solid #10b981; padding-bottom: 4px; display: flex; justify-content: space-between;">
                    <span>🏥 ${object.name}</span>
                  </div>
                  <div style="font-size: 11px; color: #cbd5e1; margin-top: 8px; display: flex; justify-content: space-between;">
                    <span>Population at Risk:</span> <span>${object.population.toLocaleString()}</span>
                  </div>
                  <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px; display: flex; justify-content: space-between;">
                    <span>Supply Remaining:</span> <span style="font-weight: 700; color: ${object.current_days_supply <= 3 ? '#ef4444' : (object.current_days_supply < 7 ? '#f59e0b' : '#10b981')}">${object.current_days_supply} Days</span>
                  </div>
                  <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px; display: flex; justify-content: space-between;">
                    <span>Nearest Port:</span> <span>${object.port_id.toUpperCase()}</span>
                  </div>
                `,
                style: {
                  backgroundColor: 'rgba(15, 23, 42, 0.85)',
                  backdropFilter: 'blur(12px)',
                  border: '1px solid #10b981',
                  borderRadius: '8px',
                  padding: '12px',
                  boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)'
                }
              };
            }
            return {
              html: `
                <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 4px; border-bottom: 1px solid #334155; padding-bottom: 4px;">${object.id.toUpperCase()}</div>
                <div style="font-size: 11px; color: #94a3b8;">Logistics Hub / Port</div>
              `,
              style: {
                backgroundColor: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(12px)',
                border: '1px solid #334155',
                borderRadius: '8px',
                padding: '12px',
                boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)'
              }
            };
          }
          const risk = object.risk_score !== undefined ? (object.risk_score * 100).toFixed(1) + '%' : 'N/A';
          const co2 = object.carbon_metrics ? object.carbon_metrics.co2_per_teu : 'N/A';
          const spotRate = object.current_spot_rate ? '$' + object.current_spot_rate.toLocaleString() : 'N/A';
          const sId = object.source_id ? object.source_id.toUpperCase() : 'UNKNOWN';
          const tId = object.target_id ? object.target_id.toUpperCase() : 'UNKNOWN';
          return {
            html: `
              <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 4px; border-bottom: 1px solid #334155; padding-bottom: 4px;">
                ${sId} ➔ ${tId}
              </div>
              <div style="font-size: 11px; color: #cbd5e1; margin-top: 8px; display: flex; justify-content: space-between;">
                <span>Risk Score:</span> <span style="font-family: monospace; color: #fbbf24;">${risk}</span>
              </div>
              <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px; display: flex; justify-content: space-between; gap: 16px;">
                <span>Carbon:</span> <span style="font-family: monospace; color: #34d399;">${co2} kg CO₂</span>
              </div>
              <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px; display: flex; justify-content: space-between; gap: 16px;">
                <span>Spot Rate:</span> <span style="font-family: monospace; color: #38bdf8;">${spotRate} / TEU</span>
              </div>
            `,
            style: {
              backgroundColor: 'rgba(15, 23, 42, 0.85)',
              backdropFilter: 'blur(12px)',
              border: '1px solid #334155',
              borderRadius: '8px',
              padding: '12px',
              boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)'
            }
          };
        }}
        style={{ backgroundColor: '#090a0c' }} // Exactly matches Carto Dark Matter ocean hex to hide the map edges seamlessly
      >
        <ReactMapGL reuseMaps mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json" />
      </DeckGL>
      <div className="absolute inset-0 pointer-events-none shadow-[inset_0_0_150px_rgba(2,6,23,1)]"></div>

      {/* Port Details Floating Panel */}
      <PortDetailsPanel />

      {/* Legend Overlay */}
      <div className="map-legend-overlay">
        <h4 style={{ margin: '0 0 10px 0', fontSize: 12, color: 'var(--text-primary)', letterSpacing: 1 }}>
          {optimizationMode === 'sustainability' ? 'CARBON EMISSIONS' : optimizationMode === 'essential' ? 'CARGO PRIORITY' : optimizationMode === 'financial' ? 'FREIGHT RATES' : 'NETWORK STATUS'}
        </h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 11, color: 'var(--text-secondary)' }}>
          {optimizationMode === 'sustainability' ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#10b981', borderRadius: 2 }} /> Eco-Friendly (&lt; 200 kg CO₂)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#a855f7', borderRadius: 2 }} /> Standard (200-300 kg CO₂)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#f43f5e', borderRadius: 2 }} /> Heavy Emissions (&gt; 300 kg CO₂)
              </div>
            </>
          ) : optimizationMode === 'essential' ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#334155', borderRadius: 2 }} /> Low Priority (&lt; 0.4)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#94a3b8', borderRadius: 2 }} /> Normal Supply (0.4 - 0.7)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#facc15', borderRadius: 2 }} /> Critical Supply (&ge; 0.7)
              </div>
            </>
          ) : optimizationMode === 'financial' ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#10b981', borderRadius: 2 }} /> Favorable (&lt; $1,000)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#f59e0b', borderRadius: 2 }} /> Elevated ($1k - $2.5k)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: '#ef4444', borderRadius: 2 }} /> Price Gouge (&ge; $2.5k)
              </div>
            </>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: 'var(--status-ok)', borderRadius: 2 }} /> Stable (Risk &lt; 45%)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: 'var(--status-warn)', borderRadius: 2 }} /> Degraded (Risk 45-70%)
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 12, height: 4, background: 'var(--status-crit)', borderRadius: 2 }} /> Critical (Risk &ge; 70%)
              </div>
            </>
          )}
          {activeSimulationPath && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
              <span style={{ width: 12, height: 4, background: 'linear-gradient(90deg, var(--brand-blue), var(--brand-indigo))', borderRadius: 2 }} /> Optimal Reroute
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
