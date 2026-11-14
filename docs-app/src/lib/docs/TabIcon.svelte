<script lang="ts">
  import TreeStructure from "phosphor-svelte/lib/TreeStructure";
</script>

<!-- The icon in the browser's tab: one tree of everything, drawn from the installed icon set, never copied. -->
<!-- An image file cannot read the page's tokens, so it is ink on a light tab and paper on a dark one. -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <style>
    svg {
      color: black;
    }
    @media (prefers-color-scheme: dark) {
      svg {
        color: white;
      }
    }
  </style>
  <TreeStructure weight="bold" size={256} />
</svg>
