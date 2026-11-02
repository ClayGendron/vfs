<script lang="ts">
  let { label = "Pluto Systems", entrance = false }: { label?: string; entrance?: boolean } = $props();
</script>

<span class="four-dot" class:entrance role="img" aria-label={label}>
  <span class="dot dot-1"></span>
  <span class="dot dot-2"></span>
  <span class="dot dot-3"></span>
  <span class="dot dot-4"></span>
</span>

<style>
  .four-dot {
    display: inline-grid;
    grid-template-columns: repeat(2, var(--mark-dot));
    gap: var(--mark-gap);
    font-size: 1em;
    line-height: 1;
  }
  .dot {
    display: block;
    width: var(--mark-dot);
    height: var(--mark-dot);
    border-radius: 999px;
  }
  .dot-1 { background: var(--mark-1); }
  .dot-2 { background: var(--mark-2); }
  .dot-3 { background: var(--mark-3); }
  .dot-4 { background: var(--mark-4); }

  .entrance .dot {
    animation: dock var(--motion-entrance) cubic-bezier(0.2, 0.8, 0.2, 1) both;
  }
  .entrance .dot-2 { animation-delay: calc(var(--motion-entrance) * 0.1); }
  .entrance .dot-3 { animation-delay: calc(var(--motion-entrance) * 0.2); }
  .entrance .dot-4 { animation-delay: calc(var(--motion-entrance) * 0.3); }
  @keyframes dock {
    from { transform: translateY(calc(-1 * var(--mark-rise))); opacity: 0; }
    to { transform: none; opacity: 1; }
  }
  @media (prefers-reduced-motion: reduce) {
    .entrance .dot { animation: none; }
  }
</style>
