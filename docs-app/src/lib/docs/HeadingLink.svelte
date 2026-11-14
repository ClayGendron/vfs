<script lang="ts">
  let { id }: { id: string } = $props();
</script>

<!-- A heading's link to itself, so a reader can copy a section's address. Shown when the heading is hovered or the link is focused. -->
<a class="docs-anchor" href={`#${id}`} aria-label="Link to this section">#</a>
