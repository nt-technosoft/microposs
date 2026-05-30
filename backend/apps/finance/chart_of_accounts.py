"""
Default Chart of Accounts setup for new tenants.
Called once during tenant onboarding.
"""

# (code, name, account_type)
DEFAULT_ACCOUNTS = [
    # Assets
    ('1000', 'Касса', 'asset'),
    ('1010', 'Банковский счёт', 'asset'),
    ('1100', 'Товарные запасы', 'asset'),
    ('1200', 'Дебиторская задолженность (покупатели)', 'asset'),
    ('1210', 'Дебиторская задолженность (прочие)', 'asset'),
    ('1300', 'Денежные средства в инвест-пуле договоров', 'asset'),

    # Liabilities
    ('2000', 'Кредиторская задолженность (поставщики)', 'liability'),
    ('2100', 'Задолженность перед инвесторами', 'liability'),
    ('2200', 'Консигнационные обязательства', 'liability'),

    # Equity
    ('3000', 'Собственный капитал', 'equity'),
    ('3001', 'Изъятие капитала владельца', 'equity'),
    ('3100', 'Инвестиционный капитал (Мудараба)', 'equity'),
    ('3110', 'Инвестиционный капитал (Мушарака)', 'equity'),
    ('3200', 'Нераспределённая прибыль', 'equity'),

    # Income
    ('4000', 'Выручка от продаж', 'income'),
    ('4100', 'Прочие доходы', 'income'),

    # Expenses
    ('5000', 'Себестоимость проданных товаров', 'expense'),
    ('5100', 'Списание товаров', 'expense'),
    ('5200', 'Скидки предоставленные', 'expense'),
    ('5300', 'Операционные расходы', 'expense'),
]


def setup_chart_of_accounts(tenant_id: int) -> list:
    """
    Create default chart of accounts for a tenant.
    Idempotent — skips existing codes.
    """
    from .models import Account

    created = []
    for code, name, account_type in DEFAULT_ACCOUNTS:
        account, was_created = Account.objects.get_or_create(
            tenant_id=tenant_id,
            code=code,
            defaults={
                'name': name,
                'account_type': account_type,
                'is_system': True,
            },
        )
        if was_created:
            created.append(account)

    return created
