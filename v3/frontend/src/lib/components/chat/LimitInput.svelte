<script lang="ts">
	import { Input } from '$lib/components/ui/input';
	import { Switch } from '$lib/components/ui/switch';
	import { translate as irisT, useLocale } from '$lib/i18n/context';
	import {
		MAX_CHATBOT_LIMIT,
		CHATBOT_LIMIT_ERROR,
		validChatbotLimit
	} from '$lib/utils/chatbot-limits';
	let {
		id,
		label,
		value,
		fallback,
		disabled = false,
		onChange
	}: {
		id: string;
		label: string;
		value: number | undefined;
		fallback: number;
		disabled?: boolean;
		onChange: (value: number) => void;
	} = $props();
	const locale = useLocale();
	let lastFinite = $state<number | null>(null);
	$effect(() => {
		if (value && validChatbotLimit(value)) lastFinite = value;
	});
</script>

<div class="space-y-1">
	<div class="flex items-center gap-3">
		<Input
			{id}
			type="number"
			min="0"
			max={MAX_CHATBOT_LIMIT}
			step="1"
			aria-label={label}
			class="h-8 min-w-0 flex-1 text-xs"
			value={value === 0 ? '' : String(value ?? fallback)}
			placeholder={value === 0 ? '∞' : ''}
			disabled={disabled || value === 0}
			oninput={(e) => {
				const raw = (e.currentTarget as HTMLInputElement).value;
				onChange(raw === '' ? fallback : Number(raw));
			}}
		/>
		<Switch
			checked={value === 0}
			{disabled}
			aria-label={`${label}: ${irisT('Unlimited', $locale)}`}
			onCheckedChange={(checked) => onChange(checked ? 0 : (lastFinite ?? fallback))}
		/>
		<span class="whitespace-nowrap text-xs">{irisT('Unlimited', $locale)}</span>
	</div>
	{#if value !== undefined && !validChatbotLimit(value)}<p
			role="alert"
			class="text-xs text-destructive"
		>
			{irisT(CHATBOT_LIMIT_ERROR, $locale)}
		</p>{/if}
</div>
