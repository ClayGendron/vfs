import { MoonIcon, SunIcon, MonitorIcon } from "@phosphor-icons/react"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useTheme } from "@/components/theme-provider"

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="vfs-chrome-icon"
        aria-label="Toggle theme"
        title="Theme (press d to toggle)"
      >
        <SunIcon className="size-4 dark:hidden" weight="regular" />
        <MoonIcon className="hidden size-4 dark:block" weight="regular" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-36">
        <DropdownMenuCheckboxItem
          checked={theme === "light"}
          onCheckedChange={() => setTheme("light")}
        >
          <SunIcon className="size-4" weight="regular" /> light
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={theme === "dark"}
          onCheckedChange={() => setTheme("dark")}
        >
          <MoonIcon className="size-4" weight="regular" /> dark
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={theme === "system"}
          onCheckedChange={() => setTheme("system")}
        >
          <MonitorIcon className="size-4" weight="regular" /> system
        </DropdownMenuCheckboxItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
