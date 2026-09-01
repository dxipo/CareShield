export type AppTheme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'careshield-theme'

export function getActiveTheme(): AppTheme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

export function applyTheme(theme: AppTheme): void {
  document.documentElement.dataset.theme = theme
  document.documentElement.style.colorScheme = theme
  localStorage.setItem(THEME_STORAGE_KEY, theme)
}

export function initializeTheme(): AppTheme {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  const theme: AppTheme = stored === 'dark' ? 'dark' : 'light'
  applyTheme(theme)
  return theme
}
