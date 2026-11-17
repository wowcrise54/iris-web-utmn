<!-- Observable request stage; only active processing stages animate. -->
<script lang="ts">
	let {
		label = 'Waiting for model response',
		active = true
	}: { label?: string; active?: boolean } = $props();
</script>

<div class="flex gap-2 text-xs" role="status" aria-live="polite">
	<div
		class="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary"
	>
		<!-- Empty avatar circle. The sparkle icon lives in the header,
		     using it here would compete with the shimmer for attention. -->
	</div>
	<div class="flex min-w-0 max-w-[80%] flex-col gap-1.5 rounded-md bg-muted px-3 py-2">
		<span class="break-words text-xs font-medium text-foreground">{label}{active ? '…' : ''}</span>
		{#if active}<div class="shimmer-bar" aria-hidden="true"></div>{/if}
	</div>
</div>

<style>
	/* A 100%-wide gradient stripe that translates left→right forever.
	   `background-size: 200%` puts the transparent tails outside the
	   visible area at each end so the animation never shows a hard
	   edge. `background-clip: padding-box` isn't needed — the bar has
	   no border. */
	.shimmer-bar {
		height: 6px;
		width: 100%;
		border-radius: 3px;
		background: linear-gradient(
			90deg,
			hsl(var(--muted-foreground) / 0.08) 0%,
			hsl(var(--muted-foreground) / 0.28) 50%,
			hsl(var(--muted-foreground) / 0.08) 100%
		);
		background-size: 200% 100%;
		animation: shimmer 1.4s ease-in-out infinite;
	}

	@media (prefers-reduced-motion: reduce) {
		.shimmer-bar {
			animation: none;
		}
	}

	@keyframes shimmer {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}
</style>
