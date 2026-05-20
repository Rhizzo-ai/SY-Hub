/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
        extend: {
                fontFamily: {
                        heading: ['Chivo', 'ui-sans-serif', 'system-ui', 'sans-serif'],
                        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
                        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
                },
                borderRadius: {
                        lg: 'var(--radius)',
                        md: 'calc(var(--radius) - 2px)',
                        sm: 'calc(var(--radius) - 4px)'
                },
                colors: {
                        background: 'hsl(var(--background))',
                        foreground: 'hsl(var(--foreground))',
                        card: {
                                DEFAULT: 'hsl(var(--card))',
                                foreground: 'hsl(var(--card-foreground))'
                        },
                        popover: {
                                DEFAULT: 'hsl(var(--popover))',
                                foreground: 'hsl(var(--popover-foreground))'
                        },
                        primary: {
                                DEFAULT: 'hsl(var(--primary))',
                                foreground: 'hsl(var(--primary-foreground))'
                        },
                        secondary: {
                                DEFAULT: 'hsl(var(--secondary))',
                                foreground: 'hsl(var(--secondary-foreground))'
                        },
                        muted: {
                                DEFAULT: 'hsl(var(--muted))',
                                foreground: 'hsl(var(--muted-foreground))'
                        },
                        accent: {
                                DEFAULT: 'hsl(var(--accent))',
                                foreground: 'hsl(var(--accent-foreground))'
                        },
                        destructive: {
                                DEFAULT: 'hsl(var(--destructive))',
                                foreground: 'hsl(var(--destructive-foreground))'
                        },
                        border: 'hsl(var(--border))',
                        input: 'hsl(var(--input))',
                        ring: 'hsl(var(--ring))',
                        chart: {
                                '1': 'hsl(var(--chart-1))',
                                '2': 'hsl(var(--chart-2))',
                                '3': 'hsl(var(--chart-3))',
                                '4': 'hsl(var(--chart-4))',
                                '5': 'hsl(var(--chart-5))'
                        },
                        // SY Homes brand tokens — Chat 16.5 patch.
                        // Provisional palette layered ALONGSIDE the slate
                        // baseline (Track 8 designer engagement reconciles
                        // final application). Stored as plain hex via CSS
                        // custom properties on :root in `src/index.css`,
                        // referenced here with `var(--…)` (not the
                        // shadcn `hsl(var(--…))` triplet form, since
                        // these values are full sRGB hex). Usage rules:
                        // see `design_guidelines.json#brand_palette`.
                        'sy-teal': {
                                DEFAULT: 'var(--sy-teal)',
                                hover: 'var(--sy-teal-hover)',
                                foreground: 'var(--sy-teal-foreground)',
                                // Chat 24 §R5 — extended shade ramp for status
                                // pills, button hovers and link text on the
                                // suppliers/PO surfaces. Hex values match the
                                // brand palette in design_guidelines.json.
                                100: '#d6f1ee',
                                200: '#a9e3dc',
                                600: '#0f9b8b',
                                700: '#0c7e72',
                                800: '#0a665c',
                        },
                        'sy-orange': {
                                DEFAULT: 'var(--sy-orange)',
                                hover: 'var(--sy-orange-hover)',
                                foreground: 'var(--sy-orange-foreground)',
                                100: '#fde8d3',
                                600: '#dd7a17',
                                700: '#b6620f',
                                800: '#8e4d0c',
                        },
                        'sy-grey': {
                                DEFAULT: 'var(--sy-grey)',
                                100: '#f3f4f6',
                                200: '#e5e7eb',
                                500: '#6b7280',
                                600: '#4b5563',
                                700: '#374151',
                                800: '#1f2937',
                        }
                },
                keyframes: {
                        'accordion-down': { from: { height: '0' }, to: { height: 'var(--radix-accordion-content-height)' } },
                        'accordion-up':   { from: { height: 'var(--radix-accordion-content-height)' }, to: { height: '0' } },
                        'fade-in':        { '0%': { opacity: '0', transform: 'translateY(4px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
                },
                animation: {
                        'accordion-down': 'accordion-down 0.2s ease-out',
                        'accordion-up':   'accordion-up 0.2s ease-out',
                        'fade-in':        'fade-in 180ms ease-out',
                }
        }
  },
  plugins: [require("tailwindcss-animate")],
};
