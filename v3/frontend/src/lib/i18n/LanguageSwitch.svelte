<script lang="ts">
  import { useLocale } from './context';
  const locale = useLocale();
  let saving = $state(false);
  let failed = $state(false);

  async function change(event: Event) {
    saving = true;
    failed = false;
    try {
      const response = await fetch('/locale', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ locale: (event.target as HTMLSelectElement).value })
      });
      if (!response.ok) throw new Error('Language change failed');
      window.location.reload();
    } catch {
      failed = true;
      saving = false;
    }
  }
</script>

<label class="inline-flex items-center gap-1 text-xs">
  <span class="sr-only">{$locale === 'ru' ? 'Язык интерфейса' : 'Interface language'}</span>
  <select value={$locale} onchange={change} disabled={saving}
    class="rounded-md border border-border bg-background px-2 py-1 text-foreground">
    <option value="en">English</option>
    <option value="ru">Русский</option>
  </select>
</label>
{#if failed}<span role="alert">{$locale === 'ru' ? 'Не удалось изменить язык' : 'Could not change language'}</span>{/if}
