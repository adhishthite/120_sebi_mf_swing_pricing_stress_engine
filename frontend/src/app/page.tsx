'use client';

export const dynamic = 'force-dynamic';

import {
  ArrowRight,
  ArrowsLeftRight,
  CheckCircle,
  Database,
  Lock,
  Moon,
  Play,
  Pulse,
  Shield,
  Sliders,
  Sparkle,
  Stack,
  Sun,
  Terminal,
  User,
} from '@phosphor-icons/react';
import { useEffect, useRef, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend as RechartsLegend,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const BACKEND_URL = 'http://adhishthite.c.googlers.com:8120/api';

// Interface matching config.py AppConfig
interface AppConfig {
  system_mode: string;
  market_dislocation_active: boolean;
  partial_swing_threshold_pct: number;
  portfolio_defaults: {
    liquid_ratio: number;
    semi_liquid_ratio: number;
    illiquid_ratio: number;
  };
  prc_matrix_swing_factors: {
    A_I: number;
    A_II: number;
    A_III: number;
    B_I: number;
    B_II: number;
    B_III: number;
    C_I: number;
    C_II: number;
    C_III: number;
    [key: string]: number;
  };
  transaction_cost_parameters: {
    liquid_asset: {
      base_spread_pct: number;
      price_impact_coefficient: number;
      market_depth_limit_inr: number;
    };
    semi_liquid_asset: {
      base_spread_pct: number;
      price_impact_coefficient: number;
      market_depth_limit_inr: number;
    };
    illiquid_asset: {
      base_spread_pct: number;
      price_impact_coefficient: number;
      market_depth_limit_inr: number;
    };
  };
  pii_masking_enabled: boolean;
  compliance_limits: {
    max_illiquid_exposure_pct: number;
    pan_regex: string;
    aadhaar_regex: string;
  };
}

interface TransactionRequest {
  investor_name: string;
  investor_pan: string;
  investor_aadhaar: string;
  aum: number;
  initial_nav: number;
  net_outflow_pct: number;
  portfolio_exposure: {
    liquid_ratio: number;
    semi_liquid_ratio: number;
    illiquid_ratio: number;
  };
  risk_o_meter: 'LOW' | 'MODERATE' | 'HIGH' | 'VERY_HIGH';
  prc_cell: 'A-I' | 'A-II' | 'A-III' | 'B-I' | 'B-II' | 'B-III' | 'C-I' | 'C-II' | 'C-III';
}

interface LiquidationCost {
  inr: number;
  pct: number;
}

interface LiquidationStrategyDetails {
  strategy: string;
  liquidated_amounts: {
    liquid: number;
    semi_liquid: number;
    illiquid: number;
    total: number;
  };
  transaction_costs: {
    liquid: LiquidationCost;
    semi_liquid: LiquidationCost;
    illiquid: LiquidationCost;
    total_inr: number;
    total_pct: number;
  };
  post_liquidation_exposure: {
    liquid_ratio: number;
    semi_liquid_ratio: number;
    illiquid_ratio: number;
    aum: number;
  };
  post_liquidation_compliant?: boolean;
}

interface CELPolicyEvaluation {
  compliant: boolean;
  cel_source: string;
  details: any;
}

interface SimulationResponse {
  initial_aum: number;
  initial_nav: number;
  net_outflow_pct: number;
  redemption_amount_inr: number;
  risk_o_meter: string;
  prc_cell: string;
  swing_pricing_triggered: boolean;
  applied_swing_factor_pct: number;
  swing_reason: string;
  optimal_strategy: string;
  optimal_strategy_details: LiquidationStrategyDetails;
  all_strategies: LiquidationStrategyDetails[];
  nav_impact: {
    initial_units: number;
    redemption_units: number;
    remaining_units: number;
    swung_nav: number;
    actual_cash_paid_out_inr: number;
    swing_savings_inr: number;
    remaining_assets_without_swing_inr: number;
    remaining_assets_with_swing_inr: number;
    remaining_nav_without_swing: number;
    remaining_nav_with_swing: number;
    nav_drag_without_swing_pct: number;
    nav_drag_with_swing_pct: number;
    protection_bps: number;
  };
  compliance_status: {
    overall_compliant: boolean;
    policies: {
      swing_pricing_triggers: CELPolicyEvaluation;
      portfolio_compliance: CELPolicyEvaluation;
      pii_protection: CELPolicyEvaluation;
    };
  };
  redacted_input_payload: {
    investor_name: string;
    investor_pan: string;
    investor_aadhaar: string;
    amount_inr?: number;
    transaction_type?: string;
  };
  explanation: string;
}

interface HistoricalRun {
  timestamp: string;
  request_payload: any;
  optimal_strategy: string;
  optimal_strategy_details: any;
  nav_impact: any;
  compliance_status: any;
  explanation: string;
}

const initialConfig: AppConfig = {
  system_mode: 'MOCK',
  market_dislocation_active: false,
  partial_swing_threshold_pct: 5.0,
  portfolio_defaults: {
    liquid_ratio: 0.1,
    semi_liquid_ratio: 0.4,
    illiquid_ratio: 0.5,
  },
  prc_matrix_swing_factors: {
    A_I: 0.0,
    A_II: 0.0,
    A_III: 1.5,
    B_I: 0.0,
    B_II: 1.25,
    B_III: 1.75,
    C_I: 1.5,
    C_II: 1.75,
    C_III: 2.0,
  },
  transaction_cost_parameters: {
    liquid_asset: {
      base_spread_pct: 0.05,
      price_impact_coefficient: 0.01,
      market_depth_limit_inr: 5000000000,
    },
    semi_liquid_asset: {
      base_spread_pct: 0.25,
      price_impact_coefficient: 0.15,
      market_depth_limit_inr: 1000000000,
    },
    illiquid_asset: {
      base_spread_pct: 1.5,
      price_impact_coefficient: 0.8,
      market_depth_limit_inr: 200000000,
    },
  },
  pii_masking_enabled: true,
  compliance_limits: {
    max_illiquid_exposure_pct: 35.0,
    pan_regex: '^[A-Z]{5}[0-9]{4}[A-Z]{1}$',
    aadhaar_regex: '^[0-9]{12}$',
  },
};

const initialForm: TransactionRequest = {
  investor_name: 'Adhish Thite',
  investor_pan: 'ADHIS7777T',
  investor_aadhaar: '999988887777',
  aum: 1000000000,
  initial_nav: 10.0,
  net_outflow_pct: 6.0,
  portfolio_exposure: {
    liquid_ratio: 0.1,
    semi_liquid_ratio: 0.4,
    illiquid_ratio: 0.5,
  },
  risk_o_meter: 'VERY_HIGH',
  prc_cell: 'B-III',
};

export default function Home() {
  const [isDarkMode, setIsDarkMode] = useState<boolean>(true);
  const [activeStep, setActiveStep] = useState<1 | 2>(1);

  const [config, setConfig] = useState<AppConfig>(initialConfig);
  const [form, setForm] = useState<TransactionRequest>(initialForm);

  const [_isUpdatingConfig, setIsUpdatingConfig] = useState<boolean>(false);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [isFetchingAudit, setIsFetchingAudit] = useState<boolean>(false);
  const [activeResult, setActiveResult] = useState<SimulationResponse | null>(null);
  const [auditTrail, setAuditTrail] = useState<HistoricalRun[]>([]);

  const [sandboxInput, setSandboxInput] = useState({
    name: 'Vikram Malhotra',
    pan: 'VIKRA1234M',
    aadhaar: '123456789012',
  });
  const [sandboxOutput, setSandboxOutput] = useState<any | null>(null);
  const [isRedactingSandbox, setIsRedactingSandbox] = useState<boolean>(false);

  const [consoleLogs, setConsoleLogs] = useState<string[]>([]);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  const [liquidPct, setLiquidPct] = useState<number>(10);
  const [semiLiquidPct, setSemiLiquidPct] = useState<number>(40);
  const [illiquidPct, setIlliquidPct] = useState<number>(50);

  useEffect(() => {
    const root = window.document.documentElement;
    if (isDarkMode) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [isDarkMode]);

  const addLog = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    const prefix = {
      info: '[INFO]',
      success: '[SUCCESS]',
      warning: '[WARN]',
      error: '[ERROR]',
    }[type];
    setConsoleLogs((prev) => [...prev, `[${timestamp}] ${prefix} ${message}`]);
  };

  const fetchActiveConfig = async () => {
    addLog('Fetching active configuration parameters from backend...', 'info');
    try {
      const res = await fetch(`${BACKEND_URL}/config`);
      if (res.ok) {
        const data: AppConfig = await res.json();
        setConfig(data);
        setLiquidPct(Math.round(data.portfolio_defaults.liquid_ratio * 100));
        setSemiLiquidPct(Math.round(data.portfolio_defaults.semi_liquid_ratio * 100));
        setIlliquidPct(Math.round(data.portfolio_defaults.illiquid_ratio * 100));
        addLog('Successfully retrieved active compliance configuration.', 'success');
      } else {
        throw new Error(`Failed to load: ${res.statusText}`);
      }
    } catch (e: any) {
      addLog(
        `Unreachable backend API Gateway. Working in local-simulation mode: ${e.message}`,
        'warning',
      );
    }
  };

  const updateConfigOnBackend = async (newConfig: AppConfig) => {
    setIsUpdatingConfig(true);
    addLog('Committing regulatory parameter updates to compliance backend...', 'info');
    try {
      const res = await fetch(`${BACKEND_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig),
      });
      if (res.ok) {
        const data: AppConfig = await res.json();
        setConfig(data);
        addLog('Successfully synchronized global compliance parameters on Gateway.', 'success');
      } else {
        throw new Error(`Server returned error: ${res.statusText}`);
      }
    } catch (e: any) {
      addLog(
        `Failed to sync config with backend. Saved parameters to local config memory: ${e.message}`,
        'warning',
      );
      setConfig(newConfig);
    } finally {
      setIsUpdatingConfig(false);
    }
  };

  const fetchAuditTrail = async () => {
    setIsFetchingAudit(true);
    try {
      const res = await fetch(`${BACKEND_URL}/audit-trail`);
      if (res.ok) {
        const data: HistoricalRun[] = await res.json();
        setAuditTrail(data);
        addLog(
          `Retrieved ${data.length} historical simulation records from audit ledger.`,
          'success',
        );
      }
    } catch (e: any) {
      addLog(`Could not fetch historical ledger: ${e.message}`, 'warning');
    } finally {
      setIsFetchingAudit(false);
    }
  };

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    fetchActiveConfig();
    fetchAuditTrail();
  }, []);

  useEffect(() => {
    setForm((f) => ({
      ...f,
      portfolio_exposure: {
        liquid_ratio: liquidPct / 100,
        semi_liquid_ratio: semiLiquidPct / 100,
        illiquid_ratio: illiquidPct / 100,
      },
    }));
  }, [liquidPct, semiLiquidPct, illiquidPct]);

  const executeStressSimulation = async (requestPayload: TransactionRequest) => {
    setIsSimulating(true);
    addLog(
      `Initiating redemption stress testing payload execution. Outflow: ${requestPayload.net_outflow_pct}%...`,
      'info',
    );

    const currentPayload = {
      ...requestPayload,
      aum: Number(requestPayload.aum),
      initial_nav: Number(requestPayload.initial_nav),
      net_outflow_pct: Number(requestPayload.net_outflow_pct),
      portfolio_exposure: {
        liquid_ratio: liquidPct / 100,
        semi_liquid_ratio: semiLiquidPct / 100,
        illiquid_ratio: illiquidPct / 100,
      },
    };

    try {
      const res = await fetch(`${BACKEND_URL}/simulate-stress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentPayload),
      });

      if (res.ok) {
        const result: SimulationResponse = await res.json();
        setActiveResult(result);
        addLog(
          `Stress simulation resolved. Optimal strategy: ${result.optimal_strategy}. Swing applied: ${result.applied_swing_factor_pct.toFixed(2)}%.`,
          'success',
        );
        fetchAuditTrail();
      } else {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Internal simulator error');
      }
    } catch (e: any) {
      addLog(
        `Backend simulation execution failed: ${e.message}. Executing local rule compliance engine...`,
        'warning',
      );
      runLocalSimulationFallback(currentPayload);
    } finally {
      setIsSimulating(false);
    }
  };

  const runPIISandboxTest = async () => {
    setIsRedactingSandbox(true);
    addLog('Executing PII redaction test on raw payload...', 'info');
    try {
      const res = await fetch(`${BACKEND_URL}/redact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          investor_name: sandboxInput.name,
          investor_pan: sandboxInput.pan,
          investor_aadhaar: sandboxInput.aadhaar,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setSandboxOutput(data);
        addLog(
          'PII Redactor gateway successfully scrubbed investor identity attributes.',
          'success',
        );
      } else {
        throw new Error(res.statusText);
      }
    } catch (e: any) {
      addLog(
        `Failed to contact PIIRedactor service. Executing local regex scrubbing: ${e.message}`,
        'warning',
      );
      const maskName = (n: string) => `***MASKED_INVESTOR_${n.substring(0, 2).toUpperCase()}***`;
      const maskPAN = (p: string) => `XXXXX${p.substring(5)}`;
      const maskAadhaar = (a: string) => `XXXXXXXX${a.substring(8)}`;
      setSandboxOutput({
        investor_name: maskName(sandboxInput.name),
        investor_pan: maskPAN(sandboxInput.pan),
        investor_aadhaar: maskAadhaar(sandboxInput.aadhaar),
      });
    } finally {
      setIsRedactingSandbox(false);
    }
  };

  const runLocalSimulationFallback = (payload: any) => {
    const calculatedOutflowInr = payload.aum * (payload.net_outflow_pct / 100);
    const isExempt = ['overnight', 'liquid', 'gilt', 'gilt-10yr'].includes(
      config.system_mode.toLowerCase(),
    );

    const isHighRisk = ['HIGH', 'VERY_HIGH'].includes(payload.risk_o_meter);
    const isMandatoryDislocation = config.market_dislocation_active && isHighRisk;

    let appliedSwing = 0.0;
    let reason = 'Swing pricing not active.';

    if (!isExempt) {
      if (isMandatoryDislocation) {
        const factorKey = payload.prc_cell.replace('-', '_');
        appliedSwing = config.prc_matrix_swing_factors[factorKey] || 2.0;
        reason = `SEBI Mandated full swing pricing triggered due to market dislocation (Class: ${payload.prc_cell}).`;
      } else if (payload.net_outflow_pct >= config.partial_swing_threshold_pct) {
        appliedSwing = 0.5;
        reason = `Partial swing pricing active: Net outflow (${payload.net_outflow_pct}%) breached threshold (${config.partial_swing_threshold_pct}%).`;
      }
    }

    const calculatedCosts = calculatedOutflowInr * (appliedSwing > 0 ? 0.005 : 0.002);

    const mockDetails: LiquidationStrategyDetails = {
      strategy: 'OPTIMIZED',
      liquidated_amounts: {
        liquid: calculatedOutflowInr * 0.4,
        semi_liquid: calculatedOutflowInr * 0.45,
        illiquid: calculatedOutflowInr * 0.15,
        total: calculatedOutflowInr,
      },
      transaction_costs: {
        liquid: { inr: calculatedCosts * 0.1, pct: 0.05 },
        semi_liquid: { inr: calculatedCosts * 0.3, pct: 0.25 },
        illiquid: { inr: calculatedCosts * 0.6, pct: 1.5 },
        total_inr: calculatedCosts,
        total_pct: (calculatedCosts / calculatedOutflowInr) * 100,
      },
      post_liquidation_exposure: {
        liquid_ratio: Math.max(0, payload.portfolio_exposure.liquid_ratio - 0.02),
        semi_liquid_ratio: Math.max(0, payload.portfolio_exposure.semi_liquid_ratio - 0.01),
        illiquid_ratio: Math.min(1.0, payload.portfolio_exposure.illiquid_ratio + 0.03),
        aum: payload.aum - calculatedOutflowInr,
      },
      post_liquidation_compliant:
        payload.portfolio_exposure.illiquid_ratio * 100 <=
        config.compliance_limits.max_illiquid_exposure_pct,
    };

    const swungNav = payload.initial_nav * (1 - appliedSwing / 100);

    const mockRes: SimulationResponse = {
      initial_aum: payload.aum,
      initial_nav: payload.initial_nav,
      net_outflow_pct: payload.net_outflow_pct,
      redemption_amount_inr: calculatedOutflowInr,
      risk_o_meter: payload.risk_o_meter,
      prc_cell: payload.prc_cell,
      swing_pricing_triggered: appliedSwing > 0,
      applied_swing_factor_pct: appliedSwing,
      swing_reason: reason,
      optimal_strategy: 'OPTIMIZED',
      optimal_strategy_details: mockDetails,
      all_strategies: [mockDetails],
      nav_impact: {
        initial_units: payload.aum / payload.initial_nav,
        redemption_units: calculatedOutflowInr / payload.initial_nav,
        remaining_units: (payload.aum - calculatedOutflowInr) / payload.initial_nav,
        swung_nav: swungNav,
        actual_cash_paid_out_inr: (calculatedOutflowInr / payload.initial_nav) * swungNav,
        swing_savings_inr:
          calculatedOutflowInr - (calculatedOutflowInr / payload.initial_nav) * swungNav,
        remaining_assets_without_swing_inr: payload.aum - calculatedOutflowInr - calculatedCosts,
        remaining_assets_with_swing_inr:
          payload.aum - (calculatedOutflowInr / payload.initial_nav) * swungNav - calculatedCosts,
        remaining_nav_without_swing: payload.initial_nav * 0.995,
        remaining_nav_with_swing: payload.initial_nav * 1.002,
        nav_drag_without_swing_pct: 0.5,
        nav_drag_with_swing_pct: -0.2,
        protection_bps: appliedSwing * 10,
      },
      compliance_status: {
        overall_compliant: mockDetails.post_liquidation_compliant || false,
        policies: {
          swing_pricing_triggers: {
            compliant: true,
            cel_source:
              '// Local CEL Policy Placeholder\n(outflow_pct >= config.threshold) ? swing_pricing_active == true : true',
            details: {
              rules_evaluated: [{ name: 'Swing Trigger Check', applies: true, passed: true }],
            },
          },
          portfolio_compliance: {
            compliant: mockDetails.post_liquidation_compliant || false,
            cel_source:
              '// Local CEL Portfolio Compliance\nilliquid_ratio * 100 <= config.max_illiquid_pct',
            details: {
              rules: [
                {
                  name: 'Illiquid Exposure Limit',
                  passed: mockDetails.post_liquidation_compliant,
                  illiquid_pct: payload.portfolio_exposure.illiquid_ratio * 100,
                  limit_pct: config.compliance_limits.max_illiquid_exposure_pct,
                },
              ],
            },
          },
          pii_protection: {
            compliant: true,
            cel_source: '// Local PII Policy\nname.startsWith("***") && pan.startsWith("XXXXX")',
            details: { name_valid: true, pan_valid: true, aadhaar_valid: true },
          },
        },
      },
      redacted_input_payload: {
        investor_name: `***MASKED_${payload.investor_name.substring(0, 2).toUpperCase()}***`,
        investor_pan: `XXXXX${payload.investor_pan.substring(5)}`,
        investor_aadhaar: `XXXXXXXX${payload.investor_aadhaar.substring(8)}`,
      },
      explanation: `### Local Simulation Fallback Report\n\n**Swing Status**: Swing was active at **${appliedSwing.toFixed(2)}%**.\n\n**Waterfalls**: Liquidated ₹${(calculatedOutflowInr / 10000000).toFixed(2)} Cr in assets. The optimal liquidation strategy was determined to be **OPTIMIZED**.\n\n**Compliance Checklist**:\n- PII Protection: PASS\n- Statutory triggers: PASS\n- Maximum illiquid asset ceiling: ${mockDetails.post_liquidation_compliant ? 'PASS' : 'FAIL (Threshold is 35%)'}`,
    };

    setActiveResult(mockRes);

    const fallbackAuditEntry: HistoricalRun = {
      timestamp: new Date().toISOString(),
      request_payload: mockRes.redacted_input_payload,
      optimal_strategy: mockRes.optimal_strategy,
      optimal_strategy_details: mockRes.optimal_strategy_details,
      nav_impact: mockRes.nav_impact,
      compliance_status: mockRes.compliance_status,
      explanation: mockRes.explanation,
    };

    setAuditTrail((prev) => [fallbackAuditEntry, ...prev]);
  };

  const selectPresetScenario = (id: string) => {
    addLog(`Loading Scenario Preset: ${id}...`, 'info');
    const updatedConfig = { ...config };
    let updatedForm = { ...form };

    switch (id) {
      case 'SCEN_A':
        updatedConfig.market_dislocation_active = false;
        updatedConfig.partial_swing_threshold_pct = 5.0;
        updatedConfig.pii_masking_enabled = true;

        updatedForm = {
          ...form,
          investor_name: 'High Outflow Fund',
          investor_pan: 'CORPO1234E',
          investor_aadhaar: '111122223333',
          aum: 2000000000,
          net_outflow_pct: 8.5,
          risk_o_meter: 'VERY_HIGH',
          prc_cell: 'B-III',
        };
        setLiquidPct(12);
        setSemiLiquidPct(38);
        setIlliquidPct(50);
        break;

      case 'SCEN_B':
        updatedConfig.market_dislocation_active = true;
        updatedConfig.partial_swing_threshold_pct = 5.0;

        updatedForm = {
          ...form,
          investor_name: 'Normal Redeemer LLC',
          investor_pan: 'REDEM5678A',
          investor_aadhaar: '444455556666',
          aum: 1500000000,
          net_outflow_pct: 3.5,
          risk_o_meter: 'HIGH',
          prc_cell: 'C-II',
        };
        setLiquidPct(20);
        setSemiLiquidPct(40);
        setIlliquidPct(40);
        break;

      case 'SCEN_C':
        updatedConfig.market_dislocation_active = true;

        updatedForm = {
          ...form,
          investor_name: 'Extreme Liquidation Fund',
          investor_pan: 'EXTRE9999F',
          investor_aadhaar: '888899990000',
          aum: 1000000000,
          net_outflow_pct: 25.0,
          risk_o_meter: 'VERY_HIGH',
          prc_cell: 'C-III',
        };
        setLiquidPct(5);
        setSemiLiquidPct(25);
        setIlliquidPct(70);
        break;

      case 'SCEN_D':
        updatedConfig.market_dislocation_active = false;

        updatedForm = {
          ...form,
          investor_name: 'Safe Retail Investor',
          investor_pan: 'RETAI4321Z',
          investor_aadhaar: '123400004321',
          aum: 5000000000,
          net_outflow_pct: 1.0,
          risk_o_meter: 'LOW',
          prc_cell: 'A-I',
        };
        setLiquidPct(30);
        setSemiLiquidPct(50);
        setIlliquidPct(20);
        break;
    }

    setForm(updatedForm);
    updateConfigOnBackend(updatedConfig);
    executeStressSimulation(updatedForm);
  };

  const formatINR = (value: number) => {
    if (value >= 10000000) {
      return `₹${(value / 10000000).toFixed(2)} Cr`;
    }
    if (value >= 100000) {
      return `₹${(value / 100000).toFixed(2)} Lakh`;
    }
    return `₹${value.toLocaleString('en-IN')}`;
  };

  const getCompositionChartData = () => {
    if (!activeResult) return [];
    const defaults = activeResult.optimal_strategy_details.post_liquidation_exposure;
    const preLiquid = form.portfolio_exposure.liquid_ratio * form.aum;
    const preSemi = form.portfolio_exposure.semi_liquid_ratio * form.aum;
    const preIlliquid = form.portfolio_exposure.illiquid_ratio * form.aum;

    const postLiquid = defaults.liquid_ratio * defaults.aum;
    const postSemi = defaults.semi_liquid_ratio * defaults.aum;
    const postIlliquid = defaults.illiquid_ratio * defaults.aum;

    return [
      {
        name: 'Liquid',
        'Pre-Stress': Number((preLiquid / 10000000).toFixed(2)),
        'Post-Stress': Number((postLiquid / 10000000).toFixed(2)),
      },
      {
        name: 'Semi-Liquid',
        'Pre-Stress': Number((preSemi / 10000000).toFixed(2)),
        'Post-Stress': Number((postSemi / 10000000).toFixed(2)),
      },
      {
        name: 'Illiquid',
        'Pre-Stress': Number((preIlliquid / 10000000).toFixed(2)),
        'Post-Stress': Number((postIlliquid / 10000000).toFixed(2)),
      },
    ];
  };

  const getCostsChartData = () => {
    if (!activeResult) return [];
    const costs = activeResult.optimal_strategy_details.transaction_costs;
    return [
      {
        name: 'Liquid Assets',
        'Liquidation Cost (₹ Lakh)': Number((costs.liquid.inr / 100000).toFixed(2)),
      },
      {
        name: 'Semi-Liquid Assets',
        'Liquidation Cost (₹ Lakh)': Number((costs.semi_liquid.inr / 100000).toFixed(2)),
      },
      {
        name: 'Illiquid Assets',
        'Liquidation Cost (₹ Lakh)': Number((costs.illiquid.inr / 100000).toFixed(2)),
      },
    ];
  };

  return (
    <div className='flex-1 flex flex-col h-full overflow-hidden font-sans select-none text-foreground bg-background'>
      {/* Top Cockpit Header */}
      <header className='h-12 border-b border-border bg-card px-4 flex items-center justify-between shrink-0 font-mono'>
        <div className='flex items-center gap-2'>
          <Pulse className='h-5 w-5 text-indigo-500 animate-pulse' />
          <span className='font-bold text-xs tracking-wider uppercase'>
            SEBI Swing Pricing & Outflow Stress Cockpit
          </span>
          <Badge
            variant='outline'
            className='text-[10px] h-5 py-0 px-2 border-indigo-500/30 text-indigo-400 bg-indigo-500/5 font-mono'
          >
            GATEWAY: 8120
          </Badge>
        </div>

        {/* 2-Step Selector */}
        <div className='flex bg-muted rounded p-0.5 text-xs font-semibold'>
          <button
            type='button'
            onClick={() => setActiveStep(1)}
            className={`px-4 py-1 rounded transition-all cursor-pointer ${activeStep === 1 ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'}`}
          >
            1. Setup Configuration
          </button>
          <button
            type='button'
            onClick={() => setActiveStep(2)}
            className={`px-4 py-1 rounded transition-all cursor-pointer ${activeStep === 2 ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground hover:text-foreground'}`}
          >
            2. Workspace Cockpit
          </button>
        </div>

        <div className='flex items-center gap-4 text-xs'>
          <div className='flex items-center gap-1.5 border border-border/80 px-2 py-0.5 rounded bg-muted/20'>
            <span className='h-2 w-2 rounded-full bg-emerald-500' />
            <span className='text-[10px] uppercase font-mono text-muted-foreground'>
              Gateway Live
            </span>
          </div>

          <div className='h-4 w-[1px] bg-border' />

          {/* Theme Mode Toggle */}
          <button
            type='button'
            onClick={() => setIsDarkMode(!isDarkMode)}
            className='p-1.5 hover:bg-muted rounded text-muted-foreground hover:text-foreground transition-colors cursor-pointer'
            title='Toggle theme mode'
          >
            {isDarkMode ? (
              <Sun className='h-4 w-4 text-amber-500' />
            ) : (
              <Moon className='h-4 w-4 text-indigo-500' />
            )}
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className='flex-1 flex overflow-hidden'>
        {/* ================= STEP 1: ONBOARDING & PARAMETERS SETUP ================= */}
        {activeStep === 1 && (
          <div className='flex-1 overflow-y-auto p-8 max-w-5xl mx-auto flex flex-col justify-center space-y-8 animate-fade-in-down'>
            <div className='text-center space-y-2 max-w-3xl mx-auto'>
              <h1 className='text-3xl font-extrabold tracking-tight uppercase'>
                Regulatory Parameters & Stress Configuration
              </h1>
              <p className='text-xs text-muted-foreground tracking-wide font-mono'>
                Initialize the compliance gateway with scheme metrics, Potential Risk Class (PRC)
                matrices, and SEBI-defined market parameters.
              </p>
            </div>

            <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
              {/* Scheme parameters card */}
              <Card className='shadow-sm border-border bg-card/60'>
                <CardHeader className='border-b border-border/40 pb-3'>
                  <div className='flex items-center gap-2'>
                    <Database className='h-4 w-4 text-indigo-500' />
                    <CardTitle className='text-sm font-bold uppercase tracking-wider'>
                      Scheme Dimensions & Baseline
                    </CardTitle>
                  </div>
                  <CardDescription className='text-[11px] font-mono'>
                    Define default AUM ratios and unswung valuation metrics.
                  </CardDescription>
                </CardHeader>
                <CardContent className='space-y-4 pt-4'>
                  <div className='space-y-1'>
                    <label className='text-[10px] font-bold text-muted-foreground uppercase flex justify-between font-mono'>
                      <span>Total Scheme Assets Under Management (AUM)</span>
                      <span className='text-indigo-400 font-semibold'>{formatINR(form.aum)}</span>
                    </label>
                    <Input
                      type='number'
                      value={form.aum}
                      onChange={(e) => setForm({ ...form, aum: Number(e.target.value) })}
                      className='h-9 text-xs font-mono'
                    />
                  </div>

                  <div className='space-y-1'>
                    <label className='text-[10px] font-bold text-muted-foreground uppercase flex justify-between font-mono'>
                      <span>Baseline Initial Net Asset Value (NAV)</span>
                      <span>₹{form.initial_nav.toFixed(2)}</span>
                    </label>
                    <Input
                      type='number'
                      step='0.01'
                      value={form.initial_nav}
                      onChange={(e) => setForm({ ...form, initial_nav: Number(e.target.value) })}
                      className='h-9 text-xs font-mono'
                    />
                  </div>

                  {/* Portfolio Ratio Sliders */}
                  <div className='border-t border-border/40 pt-3 space-y-3'>
                    <span className='text-[10px] font-bold text-muted-foreground uppercase tracking-wider block font-mono'>
                      Portfolio Asset Composition ratios (Must sum to 100%)
                    </span>

                    <div className='space-y-1'>
                      <div className='flex justify-between text-[11px] font-mono'>
                        <span className='text-emerald-500 font-semibold'>
                          Liquid Ratio (G-Sec, T-Bills)
                        </span>
                        <span>{liquidPct}%</span>
                      </div>
                      <Slider
                        min={0}
                        max={100}
                        step={5}
                        value={[liquidPct]}
                        onValueChange={(val) => {
                          const v = Array.isArray(val) ? val[0] : val;
                          setLiquidPct(v);
                          const rem = 100 - v;
                          setSemiLiquidPct(Math.round(rem * 0.4));
                          setIlliquidPct(Math.round(rem * 0.6));
                        }}
                      />
                    </div>

                    <div className='space-y-1'>
                      <div className='flex justify-between text-[11px] font-mono'>
                        <span className='text-amber-500 font-semibold'>
                          Semi-Liquid Ratio (AAA Corporate Bonds)
                        </span>
                        <span>{semiLiquidPct}%</span>
                      </div>
                      <Slider
                        min={0}
                        max={100 - liquidPct}
                        step={5}
                        value={[semiLiquidPct]}
                        onValueChange={(val) => {
                          const v = Array.isArray(val) ? val[0] : val;
                          setSemiLiquidPct(v);
                          setIlliquidPct(100 - liquidPct - v);
                        }}
                      />
                    </div>

                    <div className='space-y-1'>
                      <div className='flex justify-between text-[11px] font-mono'>
                        <span className='text-rose-500 font-semibold'>
                          Illiquid Ratio (High Yield, Unrated Debt)
                        </span>
                        <span>{illiquidPct}%</span>
                      </div>
                      <div className='h-1.5 w-full bg-zinc-800 rounded overflow-hidden'>
                        <div style={{ width: `${illiquidPct}%` }} className='h-full bg-rose-500' />
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* SEBI Regulatory thresholds card */}
              <Card className='shadow-sm border-border bg-card/60'>
                <CardHeader className='border-b border-border/40 pb-3'>
                  <div className='flex items-center gap-2'>
                    <Shield className='h-4 w-4 text-indigo-500' />
                    <CardTitle className='text-sm font-bold uppercase tracking-wider'>
                      Statutory Triggers & Rules
                    </CardTitle>
                  </div>
                  <CardDescription className='text-[11px] font-mono'>
                    Configure PRC classifications and threshold constants.
                  </CardDescription>
                </CardHeader>
                <CardContent className='space-y-4 pt-4'>
                  <div className='space-y-1'>
                    <label className='text-[10px] font-bold text-muted-foreground uppercase flex justify-between font-mono'>
                      <span>Potential Risk Class (PRC) Matrix Cell</span>
                      <span className='text-amber-500'>Max Credit / Duration risk</span>
                    </label>
                    <Select
                      value={form.prc_cell}
                      onValueChange={(val: any) => setForm({ ...form, prc_cell: val })}
                    >
                      <SelectTrigger className='h-9 text-xs font-mono'>
                        <SelectValue placeholder='Select Risk Class' />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='A-I' className='font-mono text-xs'>
                          Class A-I (Low Credit / Low Duration)
                        </SelectItem>
                        <SelectItem value='A-II' className='font-mono text-xs'>
                          Class A-II (Low Credit / Mid Duration)
                        </SelectItem>
                        <SelectItem value='A-III' className='font-mono text-xs'>
                          Class A-III (Low Credit / High Duration)
                        </SelectItem>
                        <SelectItem value='B-I' className='font-mono text-xs'>
                          Class B-I (Mid Credit / Low Duration)
                        </SelectItem>
                        <SelectItem value='B-II' className='font-mono text-xs'>
                          Class B-II (Mid Credit / Mid Duration)
                        </SelectItem>
                        <SelectItem value='B-III' className='font-mono text-xs'>
                          Class B-III (Mid Credit / High Duration)
                        </SelectItem>
                        <SelectItem value='C-I' className='font-mono text-xs'>
                          Class C-I (High Credit / Low Duration)
                        </SelectItem>
                        <SelectItem value='C-II' className='font-mono text-xs'>
                          Class C-II (High Credit / Mid Duration)
                        </SelectItem>
                        <SelectItem value='C-III' className='font-mono text-xs'>
                          Class C-III (High Credit / High Duration)
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className='space-y-1'>
                    <label className='text-[10px] font-bold text-muted-foreground uppercase flex justify-between font-mono'>
                      <span>Discretionary Swing pricing threshold</span>
                      <span className='text-indigo-400 font-semibold'>
                        {config.partial_swing_threshold_pct.toFixed(2)}% Outflow
                      </span>
                    </label>
                    <div className='pt-2'>
                      <Slider
                        min={1.0}
                        max={15.0}
                        step={0.5}
                        value={[config.partial_swing_threshold_pct]}
                        onValueChange={(val) => {
                          const v = Array.isArray(val) ? val[0] : val;
                          setConfig((c) => ({ ...c, partial_swing_threshold_pct: v }));
                        }}
                      />
                    </div>
                  </div>

                  <div className='flex items-center justify-between border-t border-border/40 pt-3'>
                    <div className='space-y-0.5'>
                      <label className='text-xs font-bold text-foreground uppercase tracking-wider block font-mono'>
                        Market Dislocation Active
                      </label>
                      <p className='text-[10px] text-muted-foreground max-w-xs font-mono'>
                        Statutory declaration by SEBI triggering mandatory swing pricing.
                      </p>
                    </div>
                    <Switch
                      checked={config.market_dislocation_active}
                      onCheckedChange={(checked) =>
                        setConfig((c) => ({ ...c, market_dislocation_active: checked }))
                      }
                    />
                  </div>

                  <div className='flex items-center justify-between border-t border-border/40 pt-3'>
                    <div className='space-y-0.5'>
                      <label className='text-xs font-bold text-foreground uppercase tracking-wider block font-mono'>
                        PII Scrubbing Gate
                      </label>
                      <p className='text-[10px] text-muted-foreground max-w-xs font-mono'>
                        Enable DPDP Act 2023 customer attributes masking (PAN/Aadhaar) prior to LLM
                        analysis.
                      </p>
                    </div>
                    <Switch
                      checked={config.pii_masking_enabled}
                      onCheckedChange={(checked) =>
                        setConfig((c) => ({ ...c, pii_masking_enabled: checked }))
                      }
                    />
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Launch button */}
            <div className='flex justify-center pt-2'>
              <button
                type='button'
                onClick={() => {
                  updateConfigOnBackend(config);
                  setActiveStep(2);
                }}
                className='h-10 px-8 rounded bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs uppercase tracking-widest transition-all shadow-md flex items-center gap-2 cursor-pointer'
              >
                Proceed to workspace cockpit
                <ArrowRight className='h-4 w-4' />
              </button>
            </div>
          </div>
        )}

        {/* ================= STEP 2: SPLIT-SCREEN WORKSPACE VIEW ================= */}
        {activeStep === 2 && (
          <div className='flex-1 flex overflow-hidden divide-x divide-border'>
            {/* ----------------- LEFT PANE: CONTROLS & SANDBOX ----------------- */}
            <div className='w-[380px] shrink-0 flex flex-col bg-card overflow-y-auto divide-y divide-border/60'>
              {/* Presets segment */}
              <div className='p-4 space-y-3'>
                <div className='flex items-center gap-2 text-muted-foreground'>
                  <Sliders className='h-4 w-4 text-indigo-500' />
                  <span className='text-xs font-bold uppercase tracking-wider font-mono'>
                    Scenario Presets
                  </span>
                </div>
                <div className='grid grid-cols-2 gap-2'>
                  <button
                    type='button'
                    onClick={() => selectPresetScenario('SCEN_A')}
                    className='p-2 border border-border/80 rounded bg-muted/10 hover:bg-muted/40 hover:border-indigo-500/50 text-left transition-all text-xs cursor-pointer font-mono'
                  >
                    <div className='font-bold text-indigo-400'>SCEN-A</div>
                    <div className='text-[10px] text-muted-foreground truncate'>
                      High Outflow Normal
                    </div>
                  </button>
                  <button
                    type='button'
                    onClick={() => selectPresetScenario('SCEN_B')}
                    className='p-2 border border-border/80 rounded bg-muted/10 hover:bg-muted/40 hover:border-indigo-500/50 text-left transition-all text-xs cursor-pointer font-mono'
                  >
                    <div className='font-bold text-indigo-400'>SCEN-B</div>
                    <div className='text-[10px] text-muted-foreground truncate'>
                      Normal Outflow Stressed
                    </div>
                  </button>
                  <button
                    type='button'
                    onClick={() => selectPresetScenario('SCEN_C')}
                    className='p-2 border border-border/80 rounded bg-muted/10 hover:bg-muted/40 hover:border-indigo-500/50 text-left transition-all text-xs cursor-pointer font-mono'
                  >
                    <div className='font-bold text-indigo-400'>SCEN-C</div>
                    <div className='text-[10px] text-muted-foreground truncate'>Extreme Stress</div>
                  </button>
                  <button
                    type='button'
                    onClick={() => selectPresetScenario('SCEN_D')}
                    className='p-2 border border-border/80 rounded bg-muted/10 hover:bg-muted/40 hover:border-indigo-500/50 text-left transition-all text-xs cursor-pointer font-mono'
                  >
                    <div className='font-bold text-indigo-400'>SCEN-D</div>
                    <div className='text-[10px] text-muted-foreground truncate'>
                      Safe Compliance
                    </div>
                  </button>
                </div>
              </div>

              {/* Transaction Simulator */}
              <div className='p-4 space-y-3'>
                <div className='flex items-center gap-2 text-muted-foreground'>
                  <ArrowsLeftRight className='h-4 w-4 text-indigo-500' />
                  <span className='text-xs font-bold uppercase tracking-wider font-mono'>
                    Run Custom Stress Run
                  </span>
                </div>

                <div className='space-y-2.5 pt-1 text-xs'>
                  <div className='space-y-1'>
                    <label className='text-[10px] font-bold text-muted-foreground uppercase font-mono'>
                      Investor Name
                    </label>
                    <div className='relative'>
                      <User className='absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground' />
                      <Input
                        value={form.investor_name}
                        onChange={(e) => setForm({ ...form, investor_name: e.target.value })}
                        className='h-8 pl-8 text-xs font-mono'
                      />
                    </div>
                  </div>

                  <div className='grid grid-cols-2 gap-2'>
                    <div className='space-y-1'>
                      <label className='text-[10px] font-bold text-muted-foreground uppercase font-mono'>
                        Investor PAN
                      </label>
                      <Input
                        value={form.investor_pan}
                        onChange={(e) => setForm({ ...form, investor_pan: e.target.value })}
                        className='h-8 text-xs font-mono uppercase'
                        maxLength={10}
                      />
                    </div>
                    <div className='space-y-1'>
                      <label className='text-[10px] font-bold text-muted-foreground uppercase font-mono'>
                        Aadhaar Card
                      </label>
                      <Input
                        value={form.investor_aadhaar}
                        onChange={(e) => setForm({ ...form, investor_aadhaar: e.target.value })}
                        className='h-8 text-xs font-mono'
                        maxLength={12}
                      />
                    </div>
                  </div>

                  <div className='space-y-1'>
                    <label className='text-[10px] font-bold text-muted-foreground uppercase flex justify-between font-mono'>
                      <span>Redemption Outflow %</span>
                      <span className='text-indigo-400 font-bold'>{form.net_outflow_pct}%</span>
                    </label>
                    <div className='pt-1.5'>
                      <Slider
                        min={0.5}
                        max={30.0}
                        step={0.5}
                        value={[form.net_outflow_pct]}
                        onValueChange={(val) => {
                          const v = Array.isArray(val) ? val[0] : val;
                          setForm({ ...form, net_outflow_pct: v });
                        }}
                      />
                    </div>
                  </div>

                  <div className='grid grid-cols-2 gap-2'>
                    <div className='space-y-1'>
                      <label className='text-[10px] font-bold text-muted-foreground uppercase font-mono'>
                        Risk-o-meter
                      </label>
                      <Select
                        value={form.risk_o_meter}
                        onValueChange={(val: any) => setForm({ ...form, risk_o_meter: val })}
                      >
                        <SelectTrigger className='h-8 text-[11px] font-mono'>
                          <SelectValue placeholder='Risk-o-meter' />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value='LOW' className='text-xs'>
                            LOW
                          </SelectItem>
                          <SelectItem value='MODERATE' className='text-xs'>
                            MODERATE
                          </SelectItem>
                          <SelectItem value='HIGH' className='text-xs'>
                            HIGH
                          </SelectItem>
                          <SelectItem value='VERY_HIGH' className='text-xs'>
                            VERY HIGH
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className='space-y-1'>
                      <label className='text-[10px] font-bold text-muted-foreground uppercase font-mono'>
                        PRC Risk Cell
                      </label>
                      <Select
                        value={form.prc_cell}
                        onValueChange={(val: any) => setForm({ ...form, prc_cell: val })}
                      >
                        <SelectTrigger className='h-8 text-[11px] font-mono'>
                          <SelectValue placeholder='PRC Cell' />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value='A-I' className='text-xs'>
                            A-I
                          </SelectItem>
                          <SelectItem value='A-II' className='text-xs'>
                            A-II
                          </SelectItem>
                          <SelectItem value='A-III' className='text-xs'>
                            A-III
                          </SelectItem>
                          <SelectItem value='B-I' className='text-xs'>
                            B-I
                          </SelectItem>
                          <SelectItem value='B-II' className='text-xs'>
                            B-II
                          </SelectItem>
                          <SelectItem value='B-III' className='text-xs'>
                            B-III
                          </SelectItem>
                          <SelectItem value='C-I' className='text-xs'>
                            C-I
                          </SelectItem>
                          <SelectItem value='C-II' className='text-xs'>
                            C-II
                          </SelectItem>
                          <SelectItem value='C-III' className='text-xs'>
                            C-III
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <button
                    type='button'
                    onClick={() => executeStressSimulation(form)}
                    disabled={isSimulating}
                    className='w-full h-9 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400/40 text-white rounded text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-1.5 cursor-pointer mt-2'
                  >
                    {isSimulating ? 'Processing Simulation...' : 'Submit Transaction'}
                    <Play className='h-3.5 w-3.5' />
                  </button>
                </div>
              </div>

              {/* PII Redactor Sandbox Testing Panel */}
              <div className='p-4 space-y-3'>
                <div className='flex items-center gap-2 text-muted-foreground'>
                  <Lock className='h-4 w-4 text-indigo-500' />
                  <span className='text-xs font-bold uppercase tracking-wider font-mono'>
                    PII Redactor Sandbox
                  </span>
                </div>
                <div className='space-y-2 text-xs pt-1'>
                  <div className='space-y-1'>
                    <label className='text-[10px] font-bold text-muted-foreground uppercase font-mono'>
                      Raw Input Name
                    </label>
                    <Input
                      value={sandboxInput.name}
                      onChange={(e) => setSandboxInput({ ...sandboxInput, name: e.target.value })}
                      className='h-8 text-xs font-mono'
                    />
                  </div>
                  <div className='grid grid-cols-2 gap-2'>
                    <div className='space-y-1'>
                      <label className='text-[10px] font-bold text-muted-foreground uppercase font-mono'>
                        PAN
                      </label>
                      <Input
                        value={sandboxInput.pan}
                        onChange={(e) => setSandboxInput({ ...sandboxInput, pan: e.target.value })}
                        className='h-8 text-xs font-mono uppercase'
                        maxLength={10}
                      />
                    </div>
                    <div className='space-y-1'>
                      <label className='text-[10px] font-bold text-muted-foreground uppercase font-mono'>
                        Aadhaar
                      </label>
                      <Input
                        value={sandboxInput.aadhaar}
                        onChange={(e) =>
                          setSandboxInput({ ...sandboxInput, aadhaar: e.target.value })
                        }
                        className='h-8 text-xs font-mono'
                        maxLength={12}
                      />
                    </div>
                  </div>
                  <button
                    type='button'
                    onClick={runPIISandboxTest}
                    disabled={isRedactingSandbox}
                    className='w-full h-8 bg-zinc-800 hover:bg-zinc-700 disabled:bg-zinc-800/40 border border-zinc-700 text-zinc-100 rounded text-xs font-bold uppercase font-mono flex items-center justify-center gap-1.5 cursor-pointer'
                  >
                    {isRedactingSandbox ? 'Scrubbing...' : 'Redact Payload Attributes'}
                  </button>

                  {sandboxOutput && (
                    <div className='bg-zinc-950 p-2 rounded border border-zinc-800 text-[10px] font-mono text-zinc-300 mt-2 space-y-1 overflow-x-auto'>
                      <div className='text-zinc-500 font-bold border-b border-zinc-900 pb-1 flex justify-between'>
                        <span>REDACTED GATEWAY EXECUTED</span>
                        <span className='text-emerald-500'>200 OK</span>
                      </div>
                      <div>Name: {sandboxOutput.investor_name}</div>
                      <div>PAN: {sandboxOutput.investor_pan}</div>
                      <div>Aadhaar: {sandboxOutput.investor_aadhaar}</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Historical runs list */}
              <div className='p-4 flex-1 flex flex-col min-h-[180px] overflow-hidden'>
                <div className='flex items-center justify-between pb-2 border-b border-border/40 text-muted-foreground'>
                  <div className='flex items-center gap-2'>
                    <Database className='h-4 w-4 text-indigo-500' />
                    <span className='text-xs font-bold uppercase tracking-wider font-mono'>
                      Historical runs ledger
                    </span>
                  </div>
                  <button
                    type='button'
                    onClick={fetchAuditTrail}
                    className='text-[10px] font-mono text-indigo-400 hover:underline cursor-pointer'
                    disabled={isFetchingAudit}
                  >
                    Refresh
                  </button>
                </div>
                <div className='flex-1 overflow-y-auto space-y-2 mt-2 pr-1 scrollbar-thin'>
                  {auditTrail.length === 0 ? (
                    <div className='text-center py-6 text-xs text-muted-foreground font-mono'>
                      No historical simulations recorded yet.
                    </div>
                  ) : (
                    auditTrail.map((run, idx) => (
                      <div
                        key={idx}
                        onClick={() => {
                          addLog(
                            `Loading simulated run details from timestamp ${run.timestamp}...`,
                            'info',
                          );
                          setActiveResult({
                            initial_aum: run.request_payload.amount_inr
                              ? run.request_payload.amount_inr /
                                (run.request_payload.net_outflow_pct / 100)
                              : 1000000000,
                            initial_nav: run.nav_impact?.unswung_nav || 10,
                            net_outflow_pct: run.request_payload.net_outflow_pct || 6.0,
                            redemption_amount_inr: run.request_payload.amount_inr || 60000000,
                            risk_o_meter: run.request_payload.risk_o_meter || 'VERY_HIGH',
                            prc_cell: run.request_payload.prc_cell || 'B-III',
                            swing_pricing_triggered: run.nav_impact?.swing_savings_inr > 0,
                            applied_swing_factor_pct: run.nav_impact?.protection_bps / 10 || 0.0,
                            swing_reason: 'Restored from database log.',
                            optimal_strategy: run.optimal_strategy,
                            optimal_strategy_details: run.optimal_strategy_details,
                            all_strategies: [run.optimal_strategy_details],
                            nav_impact: run.nav_impact,
                            compliance_status: run.compliance_status,
                            redacted_input_payload: run.request_payload,
                            explanation: run.explanation,
                          });
                        }}
                        className={`p-2 border rounded hover:border-indigo-500 bg-muted/5 hover:bg-muted/20 transition-all cursor-pointer text-xs font-mono space-y-1 ${
                          activeResult &&
                          activeResult.redacted_input_payload?.investor_pan ===
                            run.request_payload?.investor_pan
                            ? 'border-indigo-500 bg-indigo-500/5'
                            : 'border-border/60'
                        }`}
                      >
                        <div className='flex justify-between items-center text-[10px] text-muted-foreground'>
                          <span>{run.timestamp}</span>
                          <Badge variant='outline' className='text-[9px] scale-90 px-1 font-mono'>
                            {run.optimal_strategy}
                          </Badge>
                        </div>
                        <div className='flex justify-between'>
                          <span className='text-zinc-400'>Investor:</span>
                          <span className='font-semibold'>
                            {run.request_payload?.investor_name}
                          </span>
                        </div>
                        <div className='flex justify-between text-[10px]'>
                          <span className='text-zinc-500'>
                            Unswung: ₹
                            {(run.nav_impact?.remaining_nav_without_swing || 10).toFixed(4)}
                          </span>
                          <span className='text-indigo-400 font-bold'>
                            Swung: ₹{(run.nav_impact?.remaining_nav_with_swing || 10).toFixed(4)}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* ----------------- RIGHT PANE: STORYBOARD WORKSPACE ----------------- */}
            <div className='flex-1 flex flex-col overflow-hidden bg-background'>
              <div className='h-10 border-b border-border bg-card/60 px-4 flex items-center justify-between shrink-0 font-mono text-xs'>
                <span className='font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5'>
                  <Pulse className='h-4 w-4 text-indigo-500' />
                  Compliance Workspace Board
                </span>
                {activeResult && (
                  <div className='flex items-center gap-2'>
                    <Badge
                      variant='outline'
                      className={`text-[9px] font-mono ${activeResult.swing_pricing_triggered ? 'border-purple-500 text-purple-400 bg-purple-500/10' : 'border-zinc-500 text-zinc-500'}`}
                    >
                      {activeResult.swing_pricing_triggered
                        ? 'SWUNG_NAV_ACTIVE'
                        : 'UNSWUNG_BASE_NAV'}
                    </Badge>
                    <span className='text-[10px] text-muted-foreground font-mono'>
                      PRC Matrix: {activeResult.prc_cell}
                    </span>
                  </div>
                )}
              </div>

              {/* Workspace Content Scroller */}
              <div className='flex-1 overflow-y-auto p-4 space-y-4'>
                {activeResult ? (
                  <div className='space-y-4'>
                    {/* Summary Metrics Row */}
                    <div className='grid grid-cols-1 md:grid-cols-4 gap-3 font-mono'>
                      <Card className='border-border bg-card/40 py-2.5 px-3 space-y-1'>
                        <span className='text-[9px] font-bold text-muted-foreground uppercase block'>
                          Total Redemption Outflow
                        </span>
                        <span className='text-sm font-extrabold text-red-500'>
                          {formatINR(activeResult.redemption_amount_inr)}
                        </span>
                        <span className='text-[9px] text-muted-foreground block'>
                          ({activeResult.net_outflow_pct}% of AUM)
                        </span>
                      </Card>

                      <Card className='border-border bg-card/40 py-2.5 px-3 space-y-1'>
                        <span className='text-[9px] font-bold text-muted-foreground uppercase block'>
                          Applied Swing Pricing Factor
                        </span>
                        <span
                          className={`text-sm font-extrabold ${activeResult.applied_swing_factor_pct > 0 ? 'text-purple-400' : 'text-zinc-500'}`}
                        >
                          {activeResult.applied_swing_factor_pct.toFixed(2)}%
                        </span>
                        <span className='text-[9px] text-muted-foreground block'>
                          SEBI statutory rule
                        </span>
                      </Card>

                      <Card className='border-border bg-card/40 py-2.5 px-3 space-y-1'>
                        <span className='text-[9px] font-bold text-muted-foreground uppercase block'>
                          Net Asset Protection overlay
                        </span>
                        <span className='text-sm font-extrabold text-emerald-400'>
                          {formatINR(activeResult.nav_impact.swing_savings_inr)}
                        </span>
                        <span className='text-[9px] text-muted-foreground block'>
                          Saved for remaining unit holders
                        </span>
                      </Card>

                      <Card className='border-border bg-card/40 py-2.5 px-3 space-y-1'>
                        <span className='text-[9px] font-bold text-muted-foreground uppercase block'>
                          Post-Stress NAV Drag Impact
                        </span>
                        <span className='text-sm font-extrabold text-amber-500'>
                          {activeResult.nav_impact.protection_bps.toFixed(2)} bps
                        </span>
                        <span className='text-[9px] text-muted-foreground block'>
                          Mitigation factor drag
                        </span>
                      </Card>
                    </div>

                    {/* Step A: Data Protection (PII Masking) */}
                    <Card className='border-border bg-card/50'>
                      <CardHeader className='py-2.5 border-b border-border/40 flex flex-row items-center justify-between'>
                        <div>
                          <CardTitle className='text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 font-mono'>
                            <Lock className='h-3.5 w-3.5 text-indigo-500' />
                            Step A: Data Protection - DPDP compliance masking
                          </CardTitle>
                          <CardDescription className='text-[10px] font-mono'>
                            Checks if investor data passes encryption and PII masking gate before
                            reaching AI processors.
                          </CardDescription>
                        </div>
                        <Badge
                          variant='outline'
                          className='text-[9px] border-emerald-500/30 text-emerald-400 bg-emerald-500/5 font-mono'
                        >
                          DPDP_SECURE
                        </Badge>
                      </CardHeader>
                      <CardContent className='py-3 font-mono text-xs'>
                        <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
                          <div className='bg-zinc-950 p-2.5 rounded border border-zinc-800'>
                            <span className='text-[10px] font-bold text-red-400 block pb-1.5 border-b border-zinc-900 uppercase'>
                              Incoming Raw Payload (Gateway)
                            </span>
                            <div className='space-y-1 pt-1.5 text-[11px]'>
                              <div>
                                investor_name:{' '}
                                <span className='text-zinc-100'>{form.investor_name}</span>
                              </div>
                              <div>
                                investor_pan:{' '}
                                <span className='text-zinc-100 uppercase'>{form.investor_pan}</span>
                              </div>
                              <div>
                                investor_aadhaar:{' '}
                                <span className='text-zinc-100'>{form.investor_aadhaar}</span>
                              </div>
                            </div>
                          </div>

                          <div className='bg-zinc-950 p-2.5 rounded border border-zinc-800'>
                            <span className='text-[10px] font-bold text-emerald-400 block pb-1.5 border-b border-zinc-900 uppercase'>
                              Sanitized Masked Payload (AI Gateway)
                            </span>
                            <div className='space-y-1 pt-1.5 text-[11px]'>
                              <div>
                                investor_name:{' '}
                                <span className='text-zinc-300 font-bold'>
                                  {activeResult.redacted_input_payload.investor_name}
                                </span>
                              </div>
                              <div>
                                investor_pan:{' '}
                                <span className='text-zinc-300 font-bold'>
                                  {activeResult.redacted_input_payload.investor_pan}
                                </span>
                              </div>
                              <div>
                                investor_aadhaar:{' '}
                                <span className='text-zinc-300 font-bold'>
                                  {activeResult.redacted_input_payload.investor_aadhaar}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Status checks list */}
                        <div className='mt-3 flex gap-4 text-[10px] text-zinc-400 border-t border-border/30 pt-2.5'>
                          <div className='flex items-center gap-1'>
                            <CheckCircle className='h-3.5 w-3.5 text-emerald-500' />
                            <span>PAN scrubbed successfully</span>
                          </div>
                          <div className='flex items-center gap-1'>
                            <CheckCircle className='h-3.5 w-3.5 text-emerald-500' />
                            <span>Aadhaar scrubbed successfully</span>
                          </div>
                          <div className='flex items-center gap-1'>
                            <CheckCircle className='h-3.5 w-3.5 text-emerald-500' />
                            <span>Name masked successfully</span>
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    {/* Step B: Statutory Guardrails (CEL Engine) */}
                    <Card className='border-border bg-card/50'>
                      <CardHeader className='py-2.5 border-b border-border/40'>
                        <div className='flex items-center justify-between'>
                          <CardTitle className='text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 font-mono'>
                            <Shield className='h-3.5 w-3.5 text-indigo-500' />
                            Step B: Statutory Guardrails - CEL Policy verification
                          </CardTitle>
                          <Badge
                            variant='outline'
                            className={`text-[9px] font-mono ${activeResult.compliance_status.overall_compliant ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/5' : 'border-red-500/30 text-red-400 bg-red-500/5'}`}
                          >
                            {activeResult.compliance_status.overall_compliant
                              ? 'ALL_POLICIES_PASS'
                              : 'POLICY_VIOLATION'}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent className='py-3'>
                        <Tabs defaultValue='swing' className='w-full'>
                          <TabsList className='bg-muted p-0.5 h-8 grid grid-cols-3 text-[10px] font-mono uppercase'>
                            <TabsTrigger value='swing' className='py-1'>
                              1. SwingPricing Triggers
                            </TabsTrigger>
                            <TabsTrigger value='portfolio' className='py-1'>
                              2. Portfolio Limits
                            </TabsTrigger>
                            <TabsTrigger value='pii' className='py-1'>
                              3. PII Protection
                            </TabsTrigger>
                          </TabsList>

                          {/* Swing triggers CEL */}
                          <TabsContent
                            value='swing'
                            className='space-y-2 mt-2 font-mono text-[11px]'
                          >
                            <div className='flex justify-between items-center bg-muted/40 p-2 rounded border border-border/55'>
                              <span className='text-[10px] uppercase font-bold text-muted-foreground'>
                                Swing trigger policy evaluation:
                              </span>
                              <Badge
                                className={
                                  activeResult.compliance_status.policies.swing_pricing_triggers
                                    .compliant
                                    ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                                    : 'bg-red-500/10 text-red-500 border-red-500/20'
                                }
                                variant='outline'
                              >
                                {activeResult.compliance_status.policies.swing_pricing_triggers
                                  .compliant
                                  ? 'PASS'
                                  : 'FAIL'}
                              </Badge>
                            </div>
                            <div className='bg-zinc-950 p-2.5 rounded border border-zinc-800 text-[10px] text-zinc-400 whitespace-pre overflow-x-auto max-h-32'>
                              {
                                activeResult.compliance_status.policies.swing_pricing_triggers
                                  .cel_source
                              }
                            </div>
                          </TabsContent>

                          {/* Portfolio limits CEL */}
                          <TabsContent
                            value='portfolio'
                            className='space-y-2 mt-2 font-mono text-[11px]'
                          >
                            <div className='flex justify-between items-center bg-muted/40 p-2 rounded border border-border/55'>
                              <span className='text-[10px] uppercase font-bold text-muted-foreground'>
                                Portfolio Risk-o-meter and Illiquid Limits:
                              </span>
                              <Badge
                                className={
                                  activeResult.compliance_status.policies.portfolio_compliance
                                    .compliant
                                    ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                                    : 'bg-red-500/10 text-red-500 border-red-500/20'
                                }
                                variant='outline'
                              >
                                {activeResult.compliance_status.policies.portfolio_compliance
                                  .compliant
                                  ? 'PASS'
                                  : 'FAIL'}
                              </Badge>
                            </div>
                            <div className='bg-zinc-950 p-2.5 rounded border border-zinc-800 text-[10px] text-zinc-400 whitespace-pre overflow-x-auto max-h-32'>
                              {
                                activeResult.compliance_status.policies.portfolio_compliance
                                  .cel_source
                              }
                            </div>
                          </TabsContent>

                          {/* PII Protection CEL */}
                          <TabsContent value='pii' className='space-y-2 mt-2 font-mono text-[11px]'>
                            <div className='flex justify-between items-center bg-muted/40 p-2 rounded border border-border/55'>
                              <span className='text-[10px] uppercase font-bold text-muted-foreground'>
                                PII Scrubbing Integrity Check:
                              </span>
                              <Badge
                                className={
                                  activeResult.compliance_status.policies.pii_protection.compliant
                                    ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                                    : 'bg-red-500/10 text-red-500 border-red-500/20'
                                }
                                variant='outline'
                              >
                                {activeResult.compliance_status.policies.pii_protection.compliant
                                  ? 'PASS'
                                  : 'FAIL'}
                              </Badge>
                            </div>
                            <div className='bg-zinc-950 p-2.5 rounded border border-zinc-800 text-[10px] text-zinc-400 whitespace-pre overflow-x-auto max-h-32'>
                              {activeResult.compliance_status.policies.pii_protection.cel_source}
                            </div>
                          </TabsContent>
                        </Tabs>
                      </CardContent>
                    </Card>

                    {/* Step C: Stress Liquidation & Swing Calculation */}
                    <Card className='border-border bg-card/50'>
                      <CardHeader className='py-2.5 border-b border-border/40'>
                        <div className='flex items-center justify-between'>
                          <CardTitle className='text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 font-mono'>
                            <Stack className='h-3.5 w-3.5 text-indigo-500' />
                            Step C: Stress Liquidation & Swing pricing math
                          </CardTitle>
                          <Badge
                            variant='outline'
                            className='text-[9px] font-mono border-indigo-500/30 text-indigo-400'
                          >
                            Strategy: {activeResult.optimal_strategy}
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent className='py-3 space-y-4'>
                        {/* Liquidation waterfall breakdown table */}
                        <div className='space-y-1.5'>
                          <span className='text-[10px] font-bold text-muted-foreground uppercase tracking-wider block font-mono'>
                            Asset class liquidation drawdown waterfall details
                          </span>
                          <Table className='border border-border/60 text-xs font-mono'>
                            <TableHeader className='bg-muted/50'>
                              <TableRow>
                                <TableHead className='py-1.5 h-7 font-bold'>Asset class</TableHead>
                                <TableHead className='py-1.5 h-7 font-bold text-right'>
                                  Liquidated amount
                                </TableHead>
                                <TableHead className='py-1.5 h-7 font-bold text-right'>
                                  Spread cost
                                </TableHead>
                                <TableHead className='py-1.5 h-7 font-bold text-right'>
                                  Impact cost
                                </TableHead>
                                <TableHead className='py-1.5 h-7 font-bold text-right'>
                                  Post-stress balance
                                </TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {/* Row 1: Liquid */}
                              <TableRow>
                                <TableCell className='py-1 h-7'>Liquid (G-Sec)</TableCell>
                                <TableCell className='py-1 h-7 text-right text-foreground font-semibold'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.liquidated_amounts.liquid,
                                  )}
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-red-400'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.transaction_costs.liquid
                                      .inr,
                                  )}
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-zinc-500'>
                                  -
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-zinc-300'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.post_liquidation_exposure
                                      .liquid_ratio *
                                      activeResult.optimal_strategy_details
                                        .post_liquidation_exposure.aum,
                                  )}
                                </TableCell>
                              </TableRow>

                              {/* Row 2: Semi-Liquid */}
                              <TableRow>
                                <TableCell className='py-1 h-7'>
                                  Semi-Liquid (AAA Corporate)
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-foreground font-semibold'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.liquidated_amounts
                                      .semi_liquid,
                                  )}
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-red-400'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.transaction_costs
                                      .semi_liquid.inr,
                                  )}
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-red-400'>
                                  Included
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-zinc-300'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.post_liquidation_exposure
                                      .semi_liquid_ratio *
                                      activeResult.optimal_strategy_details
                                        .post_liquidation_exposure.aum,
                                  )}
                                </TableCell>
                              </TableRow>

                              {/* Row 3: Illiquid */}
                              <TableRow>
                                <TableCell className='py-1 h-7'>Illiquid (High Yield)</TableCell>
                                <TableCell className='py-1 h-7 text-right text-foreground font-semibold'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.liquidated_amounts
                                      .illiquid,
                                  )}
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-red-400'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.transaction_costs.illiquid
                                      .inr,
                                  )}
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-red-400'>
                                  Widening
                                </TableCell>
                                <TableCell className='py-1 h-7 text-right text-zinc-300'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.post_liquidation_exposure
                                      .illiquid_ratio *
                                      activeResult.optimal_strategy_details
                                        .post_liquidation_exposure.aum,
                                  )}
                                </TableCell>
                              </TableRow>

                              {/* Total Row */}
                              <TableRow className='bg-muted/30 font-bold border-t border-border/80'>
                                <TableCell className='py-1.5 h-8'>Total Liquidation</TableCell>
                                <TableCell className='py-1.5 h-8 text-right text-indigo-400'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.liquidated_amounts.total,
                                  )}
                                </TableCell>
                                <TableCell
                                  className='py-1.5 h-8 text-right text-red-400'
                                  colSpan={2}
                                >
                                  {formatINR(
                                    activeResult.optimal_strategy_details.transaction_costs
                                      .total_inr,
                                  )}
                                </TableCell>
                                <TableCell className='py-1.5 h-8 text-right text-indigo-400'>
                                  {formatINR(
                                    activeResult.optimal_strategy_details.post_liquidation_exposure
                                      .aum,
                                  )}
                                </TableCell>
                              </TableRow>
                            </TableBody>
                          </Table>
                        </div>

                        {/* Interactive Visualizations */}
                        <div className='grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-border/30 pt-3'>
                          {/* Chart 1: Pre vs Post Composition */}
                          <div className='space-y-1 bg-muted/10 p-2.5 rounded border border-border/50'>
                            <span className='text-[10px] font-bold text-muted-foreground uppercase font-mono block pb-1 border-b border-border/30'>
                              Portfolio Allocation ratios (Pre vs Post Stress) (₹ Cr)
                            </span>
                            <div className='h-48 pt-2'>
                              <ResponsiveContainer width='100%' height='100%'>
                                <BarChart data={getCompositionChartData()}>
                                  <CartesianGrid strokeDasharray='3 3' stroke='#2a2a2a' />
                                  <XAxis dataKey='name' stroke='#a0a0a0' fontSize={10} />
                                  <YAxis stroke='#a0a0a0' fontSize={10} />
                                  <RechartsTooltip
                                    contentStyle={{
                                      backgroundColor: '#18181b',
                                      borderColor: '#27272a',
                                      fontSize: 11,
                                    }}
                                  />
                                  <RechartsLegend wrapperStyle={{ fontSize: 10 }} />
                                  <Bar dataKey='Pre-Stress' fill='#6366f1' />
                                  <Bar dataKey='Post-Stress' fill='#a855f7' />
                                </BarChart>
                              </ResponsiveContainer>
                            </div>
                          </div>

                          {/* Chart 2: Cost Breakdown */}
                          <div className='space-y-1 bg-muted/10 p-2.5 rounded border border-border/50'>
                            <span className='text-[10px] font-bold text-muted-foreground uppercase font-mono block pb-1 border-b border-border/30'>
                              Asset Liquidation Cost breakdown (₹ Lakh)
                            </span>
                            <div className='h-48 pt-2'>
                              <ResponsiveContainer width='100%' height='100%'>
                                <BarChart data={getCostsChartData()}>
                                  <CartesianGrid strokeDasharray='3 3' stroke='#2a2a2a' />
                                  <XAxis dataKey='name' stroke='#a0a0a0' fontSize={10} />
                                  <YAxis stroke='#a0a0a0' fontSize={10} />
                                  <RechartsTooltip
                                    contentStyle={{
                                      backgroundColor: '#18181b',
                                      borderColor: '#27272a',
                                      fontSize: 11,
                                    }}
                                  />
                                  <RechartsLegend wrapperStyle={{ fontSize: 10 }} />
                                  <Bar dataKey='Liquidation Cost (₹ Lakh)' fill='#f43f5e' />
                                </BarChart>
                              </ResponsiveContainer>
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    {/* Step D: Multi-Agent Narrative Explanation */}
                    <Card className='border-border bg-card/50'>
                      <CardHeader className='py-2.5 border-b border-border/40'>
                        <div className='flex items-center justify-between'>
                          <CardTitle className='text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 font-mono'>
                            <Sparkle className='h-3.5 w-3.5 text-purple-400 fill-purple-400/20' />
                            Step D: Multi-Agent Narrative Explanation (Orchestrator Synthesis)
                          </CardTitle>
                          <Badge
                            variant='outline'
                            className='text-[9px] border-purple-500/30 text-purple-400 bg-purple-500/5 font-mono'
                          >
                            GEMINI 2.5 FLASH
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent className='py-3 text-xs leading-relaxed max-h-72 overflow-y-auto font-mono text-zinc-300 bg-zinc-950/80 rounded border border-zinc-800 whitespace-pre-wrap select-text'>
                        {activeResult.explanation}
                      </CardContent>
                    </Card>
                  </div>
                ) : (
                  <div className='py-24 border border-dashed border-border rounded flex flex-col items-center justify-center space-y-3 text-center'>
                    <Pulse className='h-10 w-10 text-muted-foreground/40 animate-pulse' />
                    <h3 className='text-sm font-bold uppercase tracking-wider text-foreground font-mono'>
                      No simulation run active
                    </h3>
                    <p className='text-xs text-muted-foreground max-w-md font-mono'>
                      Please select a preset scenario on the left controls panel or input a custom
                      transaction payload to initialize the regulatory storyboard.
                    </p>
                  </div>
                )}

                {/* Real-time compliance logs feed console */}
                <Card className='border-border bg-zinc-950 text-zinc-100 rounded overflow-hidden shadow-lg mt-4'>
                  <div className='h-8 bg-zinc-900/90 border-b border-zinc-800 px-3 flex items-center justify-between font-mono text-[10px]'>
                    <span className='font-bold text-zinc-400 uppercase flex items-center gap-1.5'>
                      <Terminal className='h-3.5 w-3.5 text-indigo-400' />
                      Compliance Gateway Audit Trace Console
                    </span>
                    <Badge
                      className='bg-indigo-950 text-indigo-300 border-indigo-800/40 text-[9px] font-mono h-5'
                      variant='outline'
                    >
                      TRACE_STREAM_ACTIVE
                    </Badge>
                  </div>
                  <CardContent className='p-3 bg-zinc-950 font-mono text-[10px] leading-relaxed h-32 overflow-y-auto space-y-1'>
                    {consoleLogs.map((log, index) => (
                      <div key={index} className='whitespace-pre-wrap select-text'>
                        {log.includes('[ERROR]') ? (
                          <span className='text-red-400'>{log}</span>
                        ) : log.includes('[WARN]') ? (
                          <span className='text-amber-400'>{log}</span>
                        ) : log.includes('[SUCCESS]') ? (
                          <span className='text-emerald-400 font-semibold'>{log}</span>
                        ) : (
                          <span className='text-zinc-400'>{log}</span>
                        )}
                      </div>
                    ))}
                    <div ref={terminalEndRef} />
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
