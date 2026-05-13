<script setup lang="ts">
import { ChevronDown, UserPlus } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import BaseSelect from '@/components/base/BaseSelect.vue'
import type { ContractRow } from '@/modules/intake/types'

interface PartnerOption {
  value: number
  label: string
}

const props = defineProps<{
  investorOptions: PartnerOption[]
  hasLinkedInvestors: boolean
  investorContractRow: ContractRow | null
  operatorContractRow: ContractRow | null
  isContractEditable?: boolean
  contractCurrency: string
  plannedBudget: string
  isEditMode: boolean
  procurementTotalInContractCurrency: number
  mudarabaRatio: number
  isRecalculationOpen: boolean
  simulatedInvestorCapitalPercent: number
  simulationRangeStyle: Record<string, string>
  simulatedInvestorProfitPercent: number
  simulatedOperatorProfitPercent: number
  hasSimulationDelta: boolean
  simulationCapitalDelta: number
  simulationProfitDelta: number
  normalizeCurrency: (value: unknown) => string
  nextCurrency: (currency: string) => string
  formatPrice: (value: number, currency?: string) => string
  formatPercent: (value: number) => string
  formatSignedPercent: (value: number) => string
  updatePairPercent: (role: ContractRow['role'], field: 'capital_percent' | 'profit_percent', rawValue: string) => void
}>()

const emit = defineEmits<{
  openInvestorInvite: []
  updateContractRole: [role: ContractRow['role'], field: 'partner_id' | 'capital_percent' | 'profit_percent', value: string | number | null]
  updateContractCurrency: [value: string]
  updatePlannedBudget: [value: string]
  toggleRecalculation: []
  setSimulationCapitalPercent: [value: string]
  resetSimulation: []
}>()

const { t } = useI18n()
</script>

<template>
  <section class="form-section">
    <div class="section-header">
      <h2 class="section-title">{{ t('procurements.agreement') }}</h2>
      <button class="btn-add-investor" type="button" :disabled="props.isContractEditable === false" @click="emit('openInvestorInvite')">
        <UserPlus :size="16" :stroke-width="2" />
        {{ t('procurements.create.addInvestor') }}
      </button>
    </div>

    <div v-if="!hasLinkedInvestors" class="investor-empty">
      <div class="investor-empty-copy">
        <strong>{{ t('procurements.create.noLinkedInvestors') }}</strong>
        <span>{{ t('procurements.create.noLinkedInvestorsHint') }}</span>
      </div>
      <button class="investor-empty-action" type="button" :disabled="props.isContractEditable === false" @click="emit('openInvestorInvite')">
        <UserPlus :size="16" :stroke-width="2" />
        {{ t('procurements.create.createInvite') }}
      </button>
    </div>

    <div class="agreement-layout">
      <div class="agreement-panel">
        <div class="field-group">
          <label class="field-label">{{ t('procurements.investor') }}</label>
          <BaseSelect
            :model-value="investorContractRow?.partner_id ?? null"
            :options="investorOptions"
            :title="t('procurements.chooseInvestor')"
            :placeholder="t('procurements.chooseInvestor')"
            :disabled="props.isContractEditable === false"
            @update:model-value="(value) => emit('updateContractRole', 'INVESTOR', 'partner_id', value as number | null)"
          />
        </div>

        <div class="field-group">
          <label class="field-label">{{ t('procurements.create.plannedAgreementBudget') }}</label>
          <div class="money-field">
            <input
              :value="plannedBudget"
              type="number"
              class="input-field money-input"
              min="0"
              step="0.01"
              :disabled="props.isContractEditable === false"
              :placeholder="normalizeCurrency(contractCurrency) === 'USD' ? '15000' : '180000000'"
              @input="emit('updatePlannedBudget', ($event.target as HTMLInputElement).value)"
            />
            <button type="button" class="currency-toggle" :disabled="props.isContractEditable === false" @click="emit('updateContractCurrency', nextCurrency(contractCurrency))">
              <span class="currency-toggle-code">{{ contractCurrency }}</span>
            </button>
          </div>
        </div>

        <div v-if="isEditMode && procurementTotalInContractCurrency > 0" class="agreement-budget-card">
          <span>{{ t('procurements.create.currentAddedAmount') }}</span>
          <strong class="tabular-nums">{{ formatPrice(procurementTotalInContractCurrency, normalizeCurrency(contractCurrency)) }}</strong>
        </div>

        <div class="formula-note">
          <span>{{ t('procurements.create.formulaNote') }}</span>
        </div>

        <div class="agreement-input-table">
          <div class="agreement-input-head">
            <span />
            <span>{{ t('procurements.investor') }}</span>
            <span>{{ t('procurements.business') }}</span>
          </div>

          <div class="agreement-input-row">
            <strong>{{ t('procurements.create.capitalPercent') }}</strong>
            <div class="field-group">
              <input
                type="number"
                class="input-field"
                :value="investorContractRow?.capital_percent ?? ''"
                min="0"
                max="100"
                step="0.0001"
                :disabled="props.isContractEditable === false"
                @input="props.updatePairPercent('INVESTOR', 'capital_percent', ($event.target as HTMLInputElement).value)"
              />
            </div>
            <div class="field-group">
              <input
                type="number"
                class="input-field"
                :value="operatorContractRow?.capital_percent ?? ''"
                min="0"
                max="100"
                step="0.0001"
                :disabled="props.isContractEditable === false"
                @input="props.updatePairPercent('OPERATOR', 'capital_percent', ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>

          <div class="agreement-input-row">
            <strong>{{ t('procurements.create.profitPercent') }}</strong>
            <div class="field-group">
              <input
                type="number"
                class="input-field"
                :value="investorContractRow?.profit_percent ?? ''"
                min="0"
                max="100"
                step="0.0001"
                :disabled="props.isContractEditable === false"
                @input="props.updatePairPercent('INVESTOR', 'profit_percent', ($event.target as HTMLInputElement).value)"
              />
            </div>
            <div class="field-group">
              <input
                type="number"
                class="input-field"
                :value="operatorContractRow?.profit_percent ?? ''"
                min="0"
                max="100"
                step="0.0001"
                :disabled="props.isContractEditable === false"
                @input="props.updatePairPercent('OPERATOR', 'profit_percent', ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>
        </div>

        <div class="formula-strip">
          <span>{{ t('procurements.create.mudarabaRatio') }}</span>
          <strong class="tabular-nums">{{ Number.isFinite(mudarabaRatio) ? mudarabaRatio.toFixed(6) : '—' }}</strong>
        </div>

        <div class="recalculation-panel" :class="{ open: isRecalculationOpen }">
          <button
            class="recalculation-toggle"
            type="button"
            :disabled="props.isContractEditable === false"
            :aria-expanded="isRecalculationOpen"
            @click="emit('toggleRecalculation')"
          >
            <span class="recalculation-toggle-copy">
              <span class="panel-kicker">{{ t('procurements.create.recalculation') }}</span>
              <strong>{{ t('procurements.create.recalculationTitle') }}</strong>
              <span>{{ t('procurements.create.recalculationHint') }}</span>
            </span>
            <span class="recalculation-toggle-action">
              {{ isRecalculationOpen ? t('common.close') : t('procurements.create.rules') }}
              <ChevronDown class="recalculation-chevron" :size="18" :stroke-width="2" />
            </span>
          </button>

          <div v-if="isRecalculationOpen" class="recalculation-details">
            <div class="rule-list">
              <div>
                <strong>{{ t('procurements.create.rulePlanTitle') }}</strong>
                <span>{{ t('procurements.create.rulePlanText') }}</span>
              </div>
              <div>
                <strong>{{ t('procurements.create.ruleFactTitle') }}</strong>
                <span>{{ t('procurements.create.ruleFactText') }}</span>
              </div>
              <div>
                <strong>{{ t('procurements.create.ruleOptionsTitle') }}</strong>
                <span>{{ t('procurements.create.ruleOptionsText') }}</span>
              </div>
            </div>

            <div class="split-control">
              <div class="split-header">
                <span>{{ t('procurements.create.actualInvestorCapital') }}</span>
                <strong class="tabular-nums">{{ formatPercent(simulatedInvestorCapitalPercent) }}</strong>
              </div>
              <input
                class="range-input split-range"
                type="range"
                min="0"
                max="100"
                step="0.1"
                :disabled="props.isContractEditable === false"
                :value="simulatedInvestorCapitalPercent"
                :style="simulationRangeStyle"
                @input="emit('setSimulationCapitalPercent', ($event.target as HTMLInputElement).value)"
              />
              <div class="range-labels">
                <span>{{ t('procurements.create.businessWithShare', { share: formatPercent(100 - simulatedInvestorCapitalPercent) }) }}</span>
                <span>{{ t('procurements.create.investorWithShare', { share: formatPercent(simulatedInvestorCapitalPercent) }) }}</span>
              </div>
            </div>

            <div class="simulation-result">
              <div>
                <span>{{ t('procurements.create.investorProfit') }}</span>
                <strong class="tabular-nums">{{ formatPercent(simulatedInvestorProfitPercent) }}</strong>
              </div>
              <div>
                <span>{{ t('procurements.create.businessProfit') }}</span>
                <strong class="tabular-nums">{{ formatPercent(simulatedOperatorProfitPercent) }}</strong>
              </div>
            </div>

            <div class="recalculation-note" :class="{ active: hasSimulationDelta }">
              <span v-if="hasSimulationDelta">
                {{ t('procurements.create.recalculationDelta', { capital: formatSignedPercent(simulationCapitalDelta), profit: formatSignedPercent(simulationProfitDelta) }) }}
              </span>
              <span v-else>
                {{ t('procurements.create.recalculationMatchesPlan') }}
              </span>
              <button type="button" :disabled="props.isContractEditable === false" @click="emit('resetSimulation')">{{ t('common.reset') }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.form-section { display:grid; gap: var(--space-3); }
.section-header { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); flex-wrap: wrap; }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); }
.btn-add-investor { min-height: 36px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-2); padding: 0 var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-default); color: var(--color-brand-600); background: var(--color-bg-elevated); font-weight: var(--font-medium); white-space: nowrap; }
.investor-empty { display:grid; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); border:1px dashed var(--color-border-default); background: var(--color-bg-elevated); }
.investor-empty-copy { display:grid; gap: var(--space-1); }
.investor-empty-copy strong { color: var(--color-text-primary); font-weight: var(--font-semibold); }
.investor-empty-copy span { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.investor-empty-action { min-height: 44px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-2); padding: 0 var(--space-4); border-radius: var(--radius-md); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); }
.agreement-layout { display:grid; gap: var(--space-3); }
.agreement-panel { display:grid; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.field-group { display:grid; gap: var(--space-2); }
.field-label { color: var(--color-text-secondary); font-size: var(--text-sm); }
.money-field { position: relative; }
.input-field { width:100%; min-height:44px; border:1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-elevated); padding: var(--space-3) var(--space-4); text-align:left; }
.money-input { padding-right: 88px; }
.currency-toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  height: 30px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap: 6px;
  padding: 0 10px;
  border:1px solid var(--color-border-default);
  border-radius: calc(var(--radius-md) - 2px);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}
.currency-toggle-code { font-size: var(--text-sm); line-height: 1; }
.agreement-budget-card { display:grid; gap: 4px; min-height: 48px; padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.agreement-budget-card span { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.agreement-budget-card strong { color: var(--color-text-primary); font-size: var(--text-base); }
.formula-note { display:flex; align-items:flex-start; padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-brand-50); color: var(--color-brand-700); font-size: var(--text-sm); line-height: 1.45; }
.agreement-input-table { display:grid; gap: var(--space-2); }
.agreement-input-head,
.agreement-input-row { display:grid; grid-template-columns: minmax(82px, 0.72fr) repeat(2, minmax(0, 1fr)); gap: var(--space-2); align-items:start; }
.agreement-input-head { padding: 0 var(--space-3); color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.agreement-input-row { padding: var(--space-3); border:1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); }
.agreement-input-row > strong { align-self:center; color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.formula-strip { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); color: var(--color-text-secondary); }
.formula-strip strong { color: var(--color-text-primary); }
.split-control { display:grid; gap: var(--space-2); }
.split-header { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); color: var(--color-text-secondary); font-size: var(--text-sm); }
.split-header strong { color: var(--color-text-primary); font-size: var(--text-base); }
.range-input { width:100%; accent-color: var(--color-brand-500); }
.split-range { -webkit-appearance:none; appearance:none; height: 8px; border-radius: var(--radius-full); background: linear-gradient(to right, var(--color-accent-400) 0 var(--split), var(--color-brand-500) var(--split) 100%); outline:none; }
.split-range::-webkit-slider-thumb { -webkit-appearance:none; appearance:none; width: 22px; height: 22px; border-radius: var(--radius-full); border:2px solid var(--color-brand-600); background: var(--color-bg-elevated); box-shadow: 0 2px 8px rgba(17, 24, 39, 0.16); cursor:pointer; }
.split-range::-moz-range-thumb { width: 20px; height: 20px; border-radius: var(--radius-full); border:2px solid var(--color-brand-600); background: var(--color-bg-elevated); box-shadow: 0 2px 8px rgba(17, 24, 39, 0.16); cursor:pointer; }
.range-labels { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); color: var(--color-text-tertiary); font-size: var(--text-xs); }
.recalculation-panel { display:grid; gap: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-primary); overflow:hidden; }
.recalculation-panel.open { padding-bottom: var(--space-3); }
.recalculation-toggle { width:100%; display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); text-align:left; background: var(--color-bg-primary); }
.recalculation-toggle-copy { min-width:0; display:grid; gap: 2px; }
.panel-kicker { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform: uppercase; letter-spacing: 0; }
.recalculation-toggle-copy strong { color: var(--color-text-primary); font-size: var(--text-base); font-weight: var(--font-semibold); }
.recalculation-toggle-copy span:last-child { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.recalculation-toggle-action { flex:0 0 auto; display:inline-flex; align-items:center; gap: var(--space-1); color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.recalculation-chevron { transition: transform var(--duration-fast) var(--ease-out); }
.recalculation-panel.open .recalculation-chevron { transform: rotate(180deg); }
.recalculation-details { display:grid; gap: var(--space-3); padding: 0 var(--space-3); }
.rule-list { display:grid; gap: var(--space-2); }
.rule-list > div { display:grid; gap: 2px; padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-elevated); border:1px solid var(--color-border-subtle); }
.rule-list strong { color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.rule-list span { color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.simulation-result { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); }
.simulation-result > div { display:grid; gap: var(--space-1); padding: var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.simulation-result span { color: var(--color-text-secondary); font-size: var(--text-xs); }
.simulation-result strong { color: var(--color-text-primary); font-size: var(--text-lg); }
.recalculation-note { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-elevated); color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.45; }
.recalculation-note.active { background: var(--color-accent-50); color: var(--color-accent-700); }
.recalculation-note button { flex:0 0 auto; color: var(--color-brand-600); font-weight: var(--font-semibold); white-space: nowrap; }

@media (max-width: 520px) {
  .agreement-input-head,
  .agreement-input-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .agreement-input-head span:first-child,
  .agreement-input-row > strong { grid-column: 1 / -1; }
  .section-header { align-items:flex-start; }
  .recalculation-toggle { align-items:flex-start; flex-direction:column; }
  .recalculation-note { align-items:flex-start; flex-direction:column; }
  .money-input { padding-right: 82px; }
  .currency-toggle { right: 5px; padding: 0 8px; }
}
</style>
