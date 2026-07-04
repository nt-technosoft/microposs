<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, CircleAlert, HandCoins, Landmark, RefreshCcw, Send, Users } from 'lucide-vue-next'

import { fetchInvestmentAgreements, addFundContribution, amendFundTerms, approveFundApplication, deployFund, evaluateFundPayouts, exitFundMember, fetchFundPayoutObligations, fetchInvestmentFund, previewFundApplicationApprovals, recordFundPayout, rejectFundApplication, resolveFundReview, type FundApplication, type FundApplicationApprovalPreview, type InvestmentAgreementListItem, type InvestmentFund, type PayoutObligation } from '@/api/partnerships'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useIdempotency } from '@/composables/useIdempotency'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/currency'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { generateRequestId } = useIdempotency()
const fund = ref<InvestmentFund | null>(null)
const agreements = ref<InvestmentAgreementListItem[]>([])
const obligations = ref<PayoutObligation[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const contributionMemberId = ref<number | null>(null)
const contributionAmount = ref('')
const agreementId = ref<number | null>(null)
const deploymentAmount = ref('')
const approvalAmounts = ref<Record<number, string>>({})
const selectedApplications = ref<Record<number, boolean>>({})
const approvalPreview = ref<FundApplicationApprovalPreview | null>(null)
const targetDraft = ref('')
const payoutAmounts = ref<Record<number, string>>({})
const reviewResolution = ref<'CONTINUE' | 'ORDERLY_SALE' | 'WRITE_OFF' | 'BUYOUT' | 'DISPUTE'>('CONTINUE')
let controller: AbortController | null = null

const fundId = computed(() => Number(route.params.id))
const canManageApplications = computed(() => fund.value?.permissions.can_manage_applications ?? false)
const canContribute = computed(() => fund.value?.permissions.can_confirm_contribution ?? false)
const canAmendTerms = computed(() => fund.value?.permissions.can_amend_terms ?? false)
const canDeploy = computed(() => fund.value?.permissions.can_deploy ?? false)
const canRecordPayout = computed(() => fund.value?.permissions.can_record_payout ?? false)
const deployableAgreements = computed(() => agreements.value.filter((agreement) => agreement.status === 'OPEN' || agreement.status === 'ACTIVE'))
const activeMembers = computed(() => fund.value?.members.filter((member) => member.status === 'ACTIVE') ?? [])
const contributionMember = computed(() => activeMembers.value.find((member) => member.id === contributionMemberId.value) ?? null)
const pendingApplications = computed(() => fund.value?.applications.filter((application) => application.status === 'PENDING') ?? [])
const approvedCapital = computed(() => activeMembers.value.reduce((sum, member) => sum + Number(member.approved_amount || 0), 0))
const confirmedCapital = computed(() => Number(fund.value?.position?.paid_in ?? 0))
const targetAmount = computed(() => Number(fund.value?.target_amount || 0))
const capitalProgress = computed(() => targetAmount.value > 0 ? Math.min(100, (confirmedCapital.value / targetAmount.value) * 100) : 0)
const selectedApprovalTotal = computed(() => pendingApplications.value.reduce((sum, application) => selectedApplications.value[application.id] ? sum + Number(approvalAmounts.value[application.id] || application.requested_amount || 0) : sum, 0))
const afterSelectedApprovalTotal = computed(() => approvedCapital.value + selectedApprovalTotal.value)
const managerName = computed(() => fund.value?.manager_profile_name || fund.value?.manager_partner_name || 'Управляющий')

function statusLabel(status: string): string { return { RAISING: 'Сбор капитала', DEPLOYED: 'Закрыт для взносов', CLOSED: 'Закрыт', DRAFT: 'Черновик' }[status] ?? status }
function obligationLabel(row: PayoutObligation): string { return row.kind === 'PROFIT' ? 'Прибыль к выплате' : 'Капитал к возврату' }

async function load(): Promise<void> {
  if (!Number.isFinite(fundId.value)) return
  controller?.abort(); controller = new AbortController(); loading.value = true; error.value = ''
  try {
    const fundRow = await fetchInvestmentFund(fundId.value)
    const [agreementRows, payoutRows] = await Promise.all([
      fundRow.permissions.can_deploy ? fetchInvestmentAgreements().catch(() => []) : Promise.resolve([]),
      fundRow.permissions.can_record_payout ? fetchFundPayoutObligations(fundId.value).catch(() => []) : Promise.resolve([]),
    ])
    fund.value = fundRow; agreements.value = agreementRows; obligations.value = payoutRows
    targetDraft.value = fundRow.target_amount || ''
    approvalPreview.value = null
    contributionMemberId.value ||= fundRow.members.find((member) => member.status === 'ACTIVE')?.id ?? null
    agreementId.value ||= agreementRows[0]?.id ?? null
  } catch (cause) { if ((cause as { name?: string })?.name !== 'CanceledError') error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить фонд' } finally { loading.value = false }
}

async function approve(application: FundApplication): Promise<void> {
  if (!fund.value) return
  saving.value = true
  try {
    await approveFundApplication(fund.value.id, application.id, { approved_amount: approvalAmounts.value[application.id] || application.requested_amount })
    toast.success('Заявка одобрена')
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось одобрить заявку' } finally { saving.value = false }
}

async function reject(application: FundApplication): Promise<void> {
  if (!fund.value) return
  saving.value = true
  try {
    await rejectFundApplication(fund.value.id, application.id)
    toast.success('Заявка отклонена')
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось отклонить заявку' } finally { saving.value = false }
}

async function previewSelectedApprovals(): Promise<void> {
  if (!fund.value) return
  const approvals = pendingApplications.value
    .filter((application) => selectedApplications.value[application.id])
    .map((application) => ({ application_id: application.id, approved_amount: approvalAmounts.value[application.id] || application.requested_amount }))
  if (!approvals.length) { approvalPreview.value = null; return }
  saving.value = true
  try {
    approvalPreview.value = await previewFundApplicationApprovals(fund.value.id, { approvals })
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось посчитать preview заявок' } finally { saving.value = false }
}

async function amendTarget(): Promise<void> {
  if (!fund.value || !targetDraft.value || Number(targetDraft.value) <= 0) return
  saving.value = true
  try {
    await amendFundTerms(fund.value.id, {
      target_amount: targetDraft.value,
      min_contribution_amount: fund.value.min_contribution_amount,
      visibility: fund.value.visibility,
      manager_profit_share: fund.value.current_terms?.manager_profit_share ?? '0',
      notes: 'E21 fundraising target amendment',
    })
    toast.success('Условия фонда обновлены')
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось обновить цель фонда' } finally { saving.value = false }
}

async function removeMember(member: { profile: number | null; partner: number | null }): Promise<void> {
  if (!fund.value) return
  saving.value = true
  try {
    await exitFundMember(fund.value.id, { profile_id: member.profile, partner_id: member.partner, reason: 'MANAGER_REMOVE', client_request_id: generateRequestId() })
    toast.success('Участник удалён, refund зафиксирован')
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось удалить участника' } finally { saving.value = false }
}

async function contribute(): Promise<void> {
  if (!fund.value || !contributionMember.value || Number(contributionAmount.value) <= 0) return
  saving.value = true
  try {
    await addFundContribution(fund.value.id, {
      profile_id: contributionMember.value.profile,
      partner_id: contributionMember.value.partner,
      amount: contributionAmount.value,
      currency: fund.value.currency,
      client_request_id: generateRequestId(),
    })
    toast.success('Взнос фонда зафиксирован')
    contributionAmount.value = ''
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось зафиксировать взнос' } finally { saving.value = false }
}

async function deploy(): Promise<void> {
  if (!fund.value || !agreementId.value || Number(deploymentAmount.value) <= 0) return
  saving.value = true
  try { await deployFund(fund.value.id, { agreement_id: agreementId.value, amount: deploymentAmount.value, client_request_id: generateRequestId() }); toast.success('Размещение выполнено; фонд закрыт для новых взносов'); deploymentAmount.value = ''; await load() } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось выполнить размещение' } finally { saving.value = false }
}

async function evaluate(): Promise<void> { if (!fund.value) return; try { await evaluateFundPayouts(fund.value.id); await load(); toast.success('Обязательства по выплатам обновлены') } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось проверить выплаты' } }

function remainingPayout(row: PayoutObligation): string {
  return String(Math.max(0, Number(row.amount) - Number(row.paid_amount || 0)))
}

async function recordPayout(row: PayoutObligation): Promise<void> {
  const amount = payoutAmounts.value[row.id] || remainingPayout(row)
  if (Number(amount) <= 0) return
  saving.value = true
  try {
    await recordFundPayout(row.id, { amount, evidence: 'Подтверждено управляющим офлайн' })
    toast.success('Офлайн-выплата зафиксирована и ожидает подтверждения получателем')
    payoutAmounts.value[row.id] = ''
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Не удалось зафиксировать выплату' } finally { saving.value = false }
}

async function resolveReview(): Promise<void> {
  if (!fund.value) return
  saving.value = true
  try {
    await resolveFundReview(fund.value.id, { resolution: reviewResolution.value })
    toast.success('Решение по пересмотру фонда зафиксировано')
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : 'Пока нельзя зафиксировать пересмотр фонда' } finally { saving.value = false }
}

onMounted(load); onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <main class="min-h-dvh bg-background pb-[calc(var(--bottom-nav-height)+1rem)]">
    <header class="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur"><div class="mx-auto flex min-h-14 w-full max-w-[var(--max-content-width)] items-center justify-between gap-3 px-4 sm:px-6"><div class="flex min-w-0 items-center gap-2"><Button variant="ghost" size="icon" type="button" aria-label="Назад" @click="router.back()"><ArrowLeft /></Button><div class="min-w-0"><h1 class="truncate text-lg font-semibold text-foreground">{{ fund?.name ?? 'Фонд' }}</h1><p class="text-xs text-muted-foreground">{{ fund ? statusLabel(fund.status) : 'Загрузка…' }}</p></div></div><Button variant="outline" size="icon" type="button" :disabled="loading" @click="load"><RefreshCcw :class="loading && 'animate-spin'" /></Button></div></header>
    <section v-if="loading" class="mx-auto w-full max-w-[var(--max-content-width)] px-4 py-10 text-sm text-muted-foreground sm:px-6">Загрузка фонда…</section>
    <section v-else-if="error" class="mx-auto w-full max-w-[var(--max-content-width)] px-4 py-10 text-sm text-destructive sm:px-6">{{ error }}</section>
    <section v-else-if="fund" class="mx-auto grid w-full max-w-[var(--max-content-width)] gap-6 px-4 py-5 sm:px-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div class="grid content-start gap-6"><section class="border-y border-border py-4"><div class="flex items-start justify-between gap-4"><div><p class="text-sm text-muted-foreground">Подтверждённый капитал</p><strong class="mt-1 block text-3xl tabular-nums text-foreground">{{ formatPrice(confirmedCapital, fund.currency) }}</strong></div><Landmark class="size-7 text-primary" /></div><div class="mt-3 h-2 overflow-hidden rounded-full bg-muted" v-if="targetAmount > 0"><div class="h-full rounded-full bg-primary" :style="{ width: `${capitalProgress}%` }" /></div><div class="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground"><span>Цель <strong class="text-foreground">{{ targetAmount > 0 ? formatPrice(targetAmount, fund.currency) : 'не задана' }}</strong></span><span v-if="canManageApplications">Одобрено <strong class="text-foreground">{{ formatPrice(approvedCapital, fund.currency) }}</strong></span><span>Размещено <strong class="text-foreground">{{ formatPrice(fund.position?.deployed ?? 0, fund.currency) }}</strong></span><span>Участников <strong class="text-foreground">{{ fund.active_members_count }}</strong></span><span>Заявок <strong class="text-foreground">{{ fund.pending_applications_count }}</strong></span></div><p class="mt-3 text-sm leading-relaxed text-muted-foreground">Invite: {{ fund.invite_path }} · {{ fund.visibility === 'PUBLIC_LISTING' ? 'публичный фонд' : 'закрытый фонд по ссылке' }}. Управляющий: {{ managerName }}; доля от прибыли: {{ Number(fund.current_terms?.manager_profit_share || 0) * 100 }}%.</p></section>
        <section v-if="canManageApplications"><div class="mb-3 flex items-center justify-between"><h2 class="font-semibold text-foreground">Заявки</h2><Users class="size-5 text-muted-foreground" /></div><div v-if="!pendingApplications.length" class="border-y border-border py-4 text-sm text-muted-foreground">Новых заявок нет.</div><div v-else class="divide-y divide-border border-y border-border"><div v-for="application in pendingApplications" :key="application.id" class="grid gap-2 py-3 sm:grid-cols-[auto_1fr_auto]"><input v-model="selectedApplications[application.id]" type="checkbox" class="mt-1 size-4 rounded border-input" :aria-label="`Выбрать заявку ${application.partner_name}`" /><span><strong class="block text-sm text-foreground">{{ application.partner_name }}</strong><span class="text-xs text-muted-foreground">Запрос: {{ formatPrice(application.requested_amount, application.currency) }}</span></span><span class="flex gap-2"><Input v-model="approvalAmounts[application.id]" class="w-28" inputmode="decimal" :placeholder="application.requested_amount" /><Button size="sm" type="button" :disabled="saving" @click="approve(application)">Одобрить</Button><Button size="sm" variant="outline" type="button" :disabled="saving" @click="reject(application)">Отклонить</Button></span></div><div class="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"><span class="text-muted-foreground">Выбрано к одобрению: <strong class="text-foreground">{{ formatPrice(selectedApprovalTotal, fund.currency) }}</strong>; после одобрения: <strong class="text-foreground">{{ formatPrice(afterSelectedApprovalTotal, fund.currency) }}</strong></span><Button size="sm" variant="outline" type="button" :disabled="saving || selectedApprovalTotal <= 0" @click="previewSelectedApprovals">Проверить пачку</Button></div><p v-if="approvalPreview" class="pb-3 text-xs" :class="approvalPreview.exceeds_target ? 'text-destructive' : 'text-muted-foreground'">{{ approvalPreview.exceeds_target ? 'Пачка превышает цель фонда — сначала измените условия.' : 'Пачка укладывается в текущую цель фонда.' }} После одобрения: {{ formatPrice(approvalPreview.after_approved_amount, approvalPreview.currency) }}</p></div></section>
        <section><div class="mb-3 flex items-center justify-between"><h2 class="font-semibold text-foreground">{{ canManageApplications ? 'Позиции участников' : 'Моя позиция' }}</h2><Users class="size-5 text-muted-foreground" /></div><div v-if="!fund.positions.length" class="border-y border-border py-4 text-sm text-muted-foreground">Позиция появится после одобрения заявки и подтверждения взноса.</div><div v-else class="divide-y divide-border border-y border-border"><div v-for="row in fund.positions" :key="row.id" class="grid gap-2 py-3 sm:grid-cols-[1fr_auto_auto]"><span><strong class="block text-sm text-foreground">{{ row.partner_name }}</strong><span class="text-xs text-muted-foreground">{{ (Number(row.capital_share) * 100).toFixed(2) }}% фактического капитала</span></span><span class="text-sm tabular-nums text-foreground">{{ formatPrice(row.paid_in, row.currency) }} внесено</span><span class="flex items-center justify-between gap-2 text-sm tabular-nums text-foreground sm:justify-end"><span class="text-right"><strong class="block font-semibold">{{ formatPrice(row.capital_return_available_uzs, 'UZS') }}</strong><span class="block text-xs text-muted-foreground">капитал к возврату · прибыль {{ formatPrice(row.profit_available_uzs, 'UZS') }}</span></span><Button v-if="canManageApplications" size="sm" variant="outline" type="button" :disabled="saving" @click="removeMember(row)">Убрать</Button></span></div></div></section>
        <section v-if="canRecordPayout"><div class="mb-3 flex items-center justify-between"><h2 class="font-semibold text-foreground">Выплаты и пересмотр</h2><Button variant="outline" size="sm" type="button" @click="evaluate"><HandCoins data-icon="inline-start" /> Проверить</Button></div><div v-if="!obligations.length" class="border-y border-border py-5 text-sm text-muted-foreground">Нет обязательств к действию. Проверка не переводит деньги автоматически.</div><div v-else class="divide-y divide-border border-y border-border"><div v-for="row in obligations" :key="row.id" class="grid gap-2 py-3 sm:grid-cols-[1fr_auto]"><span><strong class="block text-sm text-foreground">{{ obligationLabel(row) }}</strong><span class="text-xs text-muted-foreground">{{ row.recipient_name }} · срок {{ new Date(row.due_at).toLocaleDateString() }}</span></span><span class="text-right text-sm font-semibold tabular-nums text-foreground">{{ formatPrice(row.amount, row.currency) }}<span class="block text-xs font-normal text-muted-foreground">Выплачено {{ formatPrice(row.paid_amount || 0, row.currency) }} · {{ row.status }}</span></span><div v-if="row.status === 'PENDING' || row.status === 'DISPUTED'" class="flex gap-2 sm:col-span-2"><Input v-model="payoutAmounts[row.id]" inputmode="decimal" :placeholder="`Сумма (остаток ${remainingPayout(row)})`" /><Button variant="outline" size="sm" type="button" :disabled="saving" @click="recordPayout(row)">Зафиксировать офлайн</Button></div></div></div><div v-if="fund.current_terms?.review_at" class="mt-4 flex flex-wrap items-center gap-2"><select v-model="reviewResolution" class="h-9 rounded-md border border-input bg-background px-2 text-sm"><option value="CONTINUE">Продолжить</option><option value="ORDERLY_SALE">План распродажи</option><option value="WRITE_OFF">Зафиксировать убыток</option><option value="BUYOUT">Добровольный выкуп</option><option value="DISPUTE">Зафиксировать спор</option></select><Button variant="outline" size="sm" type="button" :disabled="saving" @click="resolveReview">Зафиксировать пересмотр</Button></div></section>
      </div>
      <aside v-if="canAmendTerms || canContribute || canDeploy" class="grid content-start gap-5"><section v-if="canAmendTerms" class="grid gap-3 border border-border p-4"><h2 class="font-semibold text-foreground">Условия сбора</h2><Input v-model="targetDraft" inputmode="decimal" placeholder="Цель фонда" /><p class="text-xs leading-relaxed text-muted-foreground">Если заявок больше текущей цели, сначала явно измените цель фонда. После размещения условия сбора закрываются.</p><Button variant="outline" type="button" :disabled="saving" @click="amendTarget">Обновить цель</Button></section><section v-if="canContribute" class="grid gap-3 border border-border p-4"><h2 class="font-semibold text-foreground">Подтвердить взнос</h2><select v-model="contributionMemberId" class="h-10 rounded-md border border-input bg-background px-3 text-sm"><option v-for="member in activeMembers" :key="member.id" :value="member.id">{{ member.partner_name }} · лимит {{ formatPrice(member.approved_amount, fund.currency) }}</option></select><Input v-model="contributionAmount" inputmode="decimal" placeholder="Сумма" /><Button type="button" :disabled="saving || !contributionMemberId" @click="contribute"><HandCoins data-icon="inline-start" /> Внести</Button></section><section v-if="canDeploy" class="grid gap-3 border border-border p-4"><h2 class="font-semibold text-foreground">Разместить в договор</h2><select v-model="agreementId" class="h-10 rounded-md border border-input bg-background px-3 text-sm"><option v-for="agreement in deployableAgreements" :key="agreement.id" :value="agreement.id">Договор #{{ agreement.id }} · {{ agreement.currency }}</option></select><Input v-model="deploymentAmount" inputmode="decimal" placeholder="Сумма размещения" /><p class="text-xs leading-relaxed text-muted-foreground"><CircleAlert class="mr-1 inline size-3.5" />Бизнес увидит фонд как одного инвестора. После первого размещения заявки и новые взносы блокируются.</p><Button type="button" :disabled="saving" @click="deploy"><Send data-icon="inline-start" /> Разместить</Button></section></aside>
    </section>
  </main>
</template>
