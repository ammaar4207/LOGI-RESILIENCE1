import { create } from 'zustand';
import { persist, devtools } from 'zustand/middleware';

export const useStore = create(
  devtools(
    persist(
      (set, get) => ({
        // ── Live Data ──────────────────────────────────────────────────────────
        metrics: [],
        history: [],
        disruptions: [],
        meta: {
          status: 'CONNECTING...',
          nodes: 0,
          edges: 0,
          updated: 'N/A',
          resilience: null,
        },
        aisShips: [],
        camps: [],

        // ── UI State ───────────────────────────────────────────────────────────
        optimizationMode: 'resilience',
        activeTab: 'map',            // map | risk | carbon | timeline | network
        activeSimulationPath: null,
        selectedPortId: null,        // Port clicked on map — drives PortDetailsPanel
        mapViewState: null,          // DeckGL view state for programmatic zoom-to-port
        forecastDays: 0,             // 0 = Live, 1-14 = Future prediction
        forecastData: null,          // Holds the predicted payload
        agentProposal: null,         // Holds active agent mitigation proposal

        // ── Auth ───────────────────────────────────────────────────────────────
        token: localStorage.getItem('auth_token') || 'mock-admin-token',
        role: localStorage.getItem('auth_role') || 'admin',
        securityLogs: ['[Auth] System initialized in mock bypass mode.'],

        // ── Notifications ──────────────────────────────────────────────────────
        notifications: [],           // {id, type, title, message, timestamp}
        wsStatus: 'CONNECTING',      // CONNECTING | OPEN | RECONNECTING | FAILED

        // ── Actions: Data ──────────────────────────────────────────────────────
        setMetrics: (metrics) => set({ metrics }),
        setHistory: (history) => set({ history }),
        setDisruptions: (disruptions) => set({ disruptions }),
        setAisShips: (aisShips) => set({ aisShips }),
        setCamps: (camps) => set({ camps }),

        updateMeta: (metaUpdates) =>
          set((state) => ({ meta: { ...state.meta, ...metaUpdates } })),

        // ── Actions: UI ────────────────────────────────────────────────────────
        setOptimizationMode: (optimizationMode) => set({ optimizationMode }),
        setActiveTab: (activeTab) => set({ activeTab }),
        setActiveSimulationPath: (activeSimulationPath) => set({ activeSimulationPath }),
        setSelectedPortId: (selectedPortId) => set({ selectedPortId }),
        setMapViewState: (mapViewState) => set({ mapViewState }),
        resetSimulation: () => set({ activeSimulationPath: null }),
        setForecastDays: (forecastDays) => set({ forecastDays }),
        setForecastData: (forecastData) => set({ forecastData }),
        setAgentProposal: (agentProposal) => set({ agentProposal }),

        // ── Actions: Auth ──────────────────────────────────────────────────────
        setToken: (token) => {
          localStorage.setItem('auth_token', token);
          set({ token });
        },
        setRole: (role) => {
          localStorage.setItem('auth_role', role);
          set({ role });
        },
        addSecurityLog: (log) =>
          set((state) => ({
            securityLogs: [
              `[${new Date().toLocaleTimeString()}] ${log}`,
              ...state.securityLogs.slice(0, 49),
            ],
          })),

        // ── Actions: WebSocket ─────────────────────────────────────────────────
        setWsStatus: (wsStatus) => set({ wsStatus }),

        // ── Actions: Notifications ─────────────────────────────────────────────
        addNotification: (notification) =>
          set((state) => ({
            notifications: [
              { id: Date.now(), timestamp: new Date().toISOString(), ...notification },
              ...state.notifications.slice(0, 19),
            ],
          })),
        dismissNotification: (id) =>
          set((state) => ({
            notifications: state.notifications.filter((n) => n.id !== id),
          })),
        clearNotifications: () => set({ notifications: [] }),
      }),
      {
        name: 'logi-resilience-store',
        // Only persist auth and UI preferences — never persist live data
        partialize: (state) => ({
          token: state.token,
          role: state.role,
          optimizationMode: state.optimizationMode,
          activeTab: state.activeTab,
          activeSimulationPath: state.activeSimulationPath,
        }),
      }
    ),
    { name: 'LogiResilienceStore' }
  )
);
