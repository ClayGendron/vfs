<script lang="ts">
  import { page } from "$app/state";
  import { Button } from "#lib/components/ui/button";
</script>

<svelte:head>
  <title>Page not found · VFS Docs</title>
</svelte:head>

<!-- The static build writes this as 404.html, the page a host answers an unknown address with. -->
<div class="mx-auto max-w-2xl px-(--gutter-stage) pt-16">
  <p class="font-mono text-xs tracking-eyebrow text-muted-foreground">{page.status}</p>
  <h1 class="mt-2 text-5xl font-bold tracking-display">
    {page.status === 404 ? "This page does not exist" : "Something went wrong"}
  </h1>
  <p class="mt-6 text-muted-foreground">
    {page.status === 404 ? "The address matches no page of the docs." : (page.error?.message ?? "")}
  </p>
  <div class="mt-8"><Button href="/">Go to the docs home</Button></div>
</div>
