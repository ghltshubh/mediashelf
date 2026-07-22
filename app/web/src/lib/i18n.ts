// Lightweight UI translation (M8.1). Driven by the same `locale` setting as
// number/date formatting (see lib/locale.ts) — language and content region stay
// independent. No dependency: a flat key→string dictionary per language, with
// English as the base and fallback. Coverage is the app chrome (nav, tabs,
// filters, view toggle); untranslated keys fall back to English, so partial
// dictionaries are safe. Extend by adding keys + languages here and swapping a
// literal for `t("key")` at the call site.

import { useLocale } from "./locale";

type Dict = Record<string, string>;

const en: Dict = {
  "nav.shelf": "Shelf",
  "nav.search": "Search",
  "nav.library": "Library",
  "nav.migrations": "Migrations",
  "nav.settings": "Settings",
  "tab.all": "All",
  "tab.movies": "Movies",
  "tab.shows": "Shows",
  "tab.music": "Music",
  "tab.podcasts": "Podcasts",
  "chip.all": "All",
  "chip.mine": "On my services",
  "chip.elsewhere": "Not on my services",
  "view.categories": "by category",
  "view.services": "by service",
};

const LANGS: Record<string, Dict> = {
  en,
  es: {
    "nav.shelf": "Estantería", "nav.search": "Buscar", "nav.library": "Biblioteca",
    "nav.migrations": "Migraciones", "nav.settings": "Ajustes",
    "tab.all": "Todo", "tab.movies": "Películas", "tab.shows": "Series",
    "tab.music": "Música", "tab.podcasts": "Podcasts",
    "chip.all": "Todo", "chip.mine": "En mis servicios", "chip.elsewhere": "Fuera de mis servicios",
    "view.categories": "por categoría", "view.services": "por servicio",
  },
  fr: {
    "nav.shelf": "Étagère", "nav.search": "Recherche", "nav.library": "Bibliothèque",
    "nav.migrations": "Migrations", "nav.settings": "Paramètres",
    "tab.all": "Tout", "tab.movies": "Films", "tab.shows": "Séries",
    "tab.music": "Musique", "tab.podcasts": "Podcasts",
    "chip.all": "Tout", "chip.mine": "Sur mes services", "chip.elsewhere": "Hors de mes services",
    "view.categories": "par catégorie", "view.services": "par service",
  },
  de: {
    "nav.shelf": "Regal", "nav.search": "Suche", "nav.library": "Bibliothek",
    "nav.migrations": "Migrationen", "nav.settings": "Einstellungen",
    "tab.all": "Alle", "tab.movies": "Filme", "tab.shows": "Serien",
    "tab.music": "Musik", "tab.podcasts": "Podcasts",
    "chip.all": "Alle", "chip.mine": "Auf meinen Diensten", "chip.elsewhere": "Nicht auf meinen Diensten",
    "view.categories": "nach Kategorie", "view.services": "nach Dienst",
  },
  it: {
    "nav.shelf": "Scaffale", "nav.search": "Cerca", "nav.library": "Libreria",
    "nav.migrations": "Migrazioni", "nav.settings": "Impostazioni",
    "tab.all": "Tutto", "tab.movies": "Film", "tab.shows": "Serie",
    "tab.music": "Musica", "tab.podcasts": "Podcast",
    "chip.all": "Tutto", "chip.mine": "Sui miei servizi", "chip.elsewhere": "Fuori dai miei servizi",
    "view.categories": "per categoria", "view.services": "per servizio",
  },
  pt: {
    "nav.shelf": "Estante", "nav.search": "Buscar", "nav.library": "Biblioteca",
    "nav.migrations": "Migrações", "nav.settings": "Configurações",
    "tab.all": "Tudo", "tab.movies": "Filmes", "tab.shows": "Séries",
    "tab.music": "Música", "tab.podcasts": "Podcasts",
    "chip.all": "Tudo", "chip.mine": "Nos meus serviços", "chip.elsewhere": "Fora dos meus serviços",
    "view.categories": "por categoria", "view.services": "por serviço",
  },
  nl: {
    "nav.shelf": "Kast", "nav.search": "Zoeken", "nav.library": "Bibliotheek",
    "nav.migrations": "Migraties", "nav.settings": "Instellingen",
    "tab.all": "Alles", "tab.movies": "Films", "tab.shows": "Series",
    "tab.music": "Muziek", "tab.podcasts": "Podcasts",
    "chip.all": "Alles", "chip.mine": "Op mijn diensten", "chip.elsewhere": "Niet op mijn diensten",
    "view.categories": "op categorie", "view.services": "op dienst",
  },
  hi: {
    "nav.shelf": "शेल्फ़", "nav.search": "खोज", "nav.library": "लाइब्रेरी",
    "nav.migrations": "माइग्रेशन", "nav.settings": "सेटिंग्स",
    "tab.all": "सभी", "tab.movies": "फ़िल्में", "tab.shows": "शोज़",
    "tab.music": "संगीत", "tab.podcasts": "पॉडकास्ट",
    "chip.all": "सभी", "chip.mine": "मेरी सेवाओं पर", "chip.elsewhere": "मेरी सेवाओं के बाहर",
    "view.categories": "श्रेणी अनुसार", "view.services": "सेवा अनुसार",
  },
  ja: {
    "nav.shelf": "棚", "nav.search": "検索", "nav.library": "ライブラリ",
    "nav.migrations": "移行", "nav.settings": "設定",
    "tab.all": "すべて", "tab.movies": "映画", "tab.shows": "番組",
    "tab.music": "音楽", "tab.podcasts": "ポッドキャスト",
    "chip.all": "すべて", "chip.mine": "契約中のサービス", "chip.elsewhere": "未契約のサービス",
    "view.categories": "カテゴリ別", "view.services": "サービス別",
  },
  ko: {
    "nav.shelf": "선반", "nav.search": "검색", "nav.library": "라이브러리",
    "nav.migrations": "마이그레이션", "nav.settings": "설정",
    "tab.all": "전체", "tab.movies": "영화", "tab.shows": "시리즈",
    "tab.music": "음악", "tab.podcasts": "팟캐스트",
    "chip.all": "전체", "chip.mine": "내 서비스", "chip.elsewhere": "내 서비스 외",
    "view.categories": "카테고리별", "view.services": "서비스별",
  },
  zh: {
    "nav.shelf": "书架", "nav.search": "搜索", "nav.library": "媒体库",
    "nav.migrations": "迁移", "nav.settings": "设置",
    "tab.all": "全部", "tab.movies": "电影", "tab.shows": "剧集",
    "tab.music": "音乐", "tab.podcasts": "播客",
    "chip.all": "全部", "chip.mine": "我的服务中", "chip.elsewhere": "不在我的服务中",
    "view.categories": "按类别", "view.services": "按服务",
  },
};

/** Map a BCP-47 locale to a language dictionary key (en-GB → en, pt-BR → pt). */
export function localeToLang(locale: string): string {
  const base = locale.toLowerCase().split("-")[0];
  return base in LANGS ? base : "en";
}

/** Returns a translator for the active locale. English is the fallback for any
    missing language or key, so the UI never shows a raw key. */
export function useT(): (key: string) => string {
  const lang = localeToLang(useLocale());
  const dict = LANGS[lang] ?? en;
  return (key: string) => dict[key] ?? en[key] ?? key;
}
