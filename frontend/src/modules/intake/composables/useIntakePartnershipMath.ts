import { computed, ref, type Ref } from 'vue'
import { ProcurementType } from '@/types/enums'
import type { Partner } from '@/api/core'
import type { ContractRow } from '@/modules/intake/types'

interface UseIntakePartnershipMathOptions {
  contractRows: Ref<ContractRow[]>
  partners: Ref<Partner[]>
  selectedType: Ref<ProcurementType>
}

export function useIntakePartnershipMath({
  contractRows,
  partners,
  selectedType,
}: UseIntakePartnershipMathOptions) {
  const simulatedInvestorCapitalPercentDraft = ref('')

  const isPartnershipType = computed(() => selectedType.value !== ProcurementType.OWN_FUNDS)
  const investorContractRow = computed(() => contractRows.value.find((row) => row.role === 'INVESTOR') ?? null)
  const operatorContractRow = computed(() => contractRows.value.find((row) => row.role === 'OPERATOR') ?? null)

  const capitalPercentTotal = computed(() => contractRows.value.reduce((sum, row) => sum + (parseFloat(row.capital_percent) || 0), 0))
  const profitTotal = computed(() => contractRows.value.reduce((sum, row) => sum + (parseFloat(row.profit_percent) || 0), 0))

  const investorCapitalPercent = computed(() => {
    return contractRows.value
      .filter((row) => row.role === 'INVESTOR')
      .reduce((sum, row) => sum + (parseFloat(row.capital_percent) || 0), 0)
  })

  const investorProfitShare = computed(() => {
    return contractRows.value
      .filter((row) => row.role === 'INVESTOR')
      .reduce((sum, row) => sum + (parseFloat(row.profit_percent) || 0), 0) / 100
  })

  const investorCapitalShare = computed(() => investorCapitalPercent.value / 100)
  const investorProfitPercent = computed(() => investorProfitShare.value * 100)
  const operatorCapitalPercent = computed(() => Math.max(0, 100 - investorCapitalPercent.value))
  const operatorProfitPercent = computed(() => Math.max(0, 100 - investorProfitPercent.value))

  const mudarabaRatio = computed(() => {
    if (!isPartnershipType.value) return 0
    if (selectedType.value === ProcurementType.MUSHARAKA) return 1
    if (investorCapitalShare.value <= 0) return Number.NaN
    return investorProfitShare.value / investorCapitalShare.value
  })

  const expectedProfitByRole = computed(() => {
    if (capitalPercentTotal.value <= 0 || Number.isNaN(mudarabaRatio.value)) return { investor: 0, operator: 0 }
    const investor = investorCapitalShare.value * mudarabaRatio.value
    return {
      investor,
      operator: 1 - investor,
    }
  })

  const simulatedInvestorCapitalPercent = computed(() => {
    if (simulatedInvestorCapitalPercentDraft.value !== '') {
      return clampPercent(simulatedInvestorCapitalPercentDraft.value)
    }
    return investorCapitalPercent.value
  })

  const simulatedInvestorProfitPercent = computed(() => {
    if (!Number.isFinite(mudarabaRatio.value)) return 0
    return Math.min(100, Math.max(0, simulatedInvestorCapitalPercent.value * mudarabaRatio.value))
  })

  const simulatedOperatorProfitPercent = computed(() => Math.max(0, 100 - simulatedInvestorProfitPercent.value))
  const simulationCapitalDelta = computed(() => simulatedInvestorCapitalPercent.value - investorCapitalPercent.value)
  const simulationProfitDelta = computed(() => simulatedInvestorProfitPercent.value - investorProfitPercent.value)
  const hasSimulationDelta = computed(() => Math.abs(simulationCapitalDelta.value) > 0.05)
  const simulationRangeStyle = computed(() => ({
    '--split': `${simulatedInvestorCapitalPercent.value}%`,
  }))

  function clampPercent(raw: string | number): number {
    const value = Number.parseFloat(String(raw))
    if (!Number.isFinite(value)) return 0
    return Math.min(100, Math.max(0, value))
  }

  function formatEditablePercent(value: number): string {
    return Number(value.toFixed(4)).toString()
  }

  function updatePairPercent(role: ContractRow['role'], field: 'capital_percent' | 'profit_percent', rawValue: string): void {
    const peerRole: ContractRow['role'] = role === 'INVESTOR' ? 'OPERATOR' : 'INVESTOR'
    const trimmedValue = rawValue.trim()

    if (trimmedValue === '') {
      contractRows.value = contractRows.value.map((row) => {
        if (row.role === role) return { ...row, [field]: '' }
        if (row.role === peerRole) return { ...row, [field]: '100' }
        return row
      })
      return
    }

    const parsedValue = Number.parseFloat(trimmedValue)
    if (!Number.isFinite(parsedValue)) return

    const currentValue = formatEditablePercent(clampPercent(parsedValue))
    const peerValue = formatEditablePercent(100 - Number.parseFloat(currentValue))

    contractRows.value = contractRows.value.map((row) => {
      if (row.role === role) return { ...row, [field]: currentValue }
      if (row.role === peerRole) return { ...row, [field]: peerValue }
      return row
    })
  }

  function formatPercent(value: number): string {
    if (!Number.isFinite(value)) return '—'
    return `${value.toLocaleString('ru-RU', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 4,
    })}%`
  }

  function formatSignedPercent(value: number): string {
    if (!Number.isFinite(value)) return '—'
    const sign = value > 0 ? '+' : value < 0 ? '-' : ''
    return `${sign}${Math.abs(value).toLocaleString('ru-RU', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 4,
    })}%`
  }

  function setSimulationCapitalPercent(raw: string | number): void {
    simulatedInvestorCapitalPercentDraft.value = clampPercent(raw).toFixed(2)
  }

  function resetSimulation(): void {
    simulatedInvestorCapitalPercentDraft.value = ''
  }

  function buildDefaultContractRows(): ContractRow[] {
    const investor = partners.value.find((partner) => partner.role === 'INVESTOR')
    const operator = partners.value.find((partner) => partner.role === 'OPERATOR')
    const currentInvestor = investorContractRow.value
    const currentOperator = operatorContractRow.value

    return [
      {
        id: crypto.randomUUID(),
        partner_id: currentInvestor?.partner_id ?? investor?.id ?? null,
        role: 'INVESTOR',
        capital_percent: currentInvestor?.capital_percent ?? '50',
        profit_percent: currentInvestor?.profit_percent ?? '50',
      },
      {
        id: crypto.randomUUID(),
        partner_id: currentOperator?.partner_id ?? operator?.id ?? null,
        role: 'OPERATOR',
        capital_percent: currentOperator?.capital_percent ?? '50',
        profit_percent: currentOperator?.profit_percent ?? '50',
      },
    ]
  }

  return {
    isPartnershipType,
    investorContractRow,
    operatorContractRow,
    capitalPercentTotal,
    profitTotal,
    investorCapitalPercent,
    investorProfitShare,
    investorCapitalShare,
    investorProfitPercent,
    operatorCapitalPercent,
    operatorProfitPercent,
    mudarabaRatio,
    expectedProfitByRole,
    simulatedInvestorCapitalPercent,
    simulatedInvestorProfitPercent,
    simulatedOperatorProfitPercent,
    simulationCapitalDelta,
    simulationProfitDelta,
    hasSimulationDelta,
    simulationRangeStyle,
    clampPercent,
    formatPercent,
    formatSignedPercent,
    setSimulationCapitalPercent,
    resetSimulation,
    buildDefaultContractRows,
    updatePairPercent,
  }
}
