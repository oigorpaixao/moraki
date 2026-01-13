export const metadata = {
  title: "Decision Engine MVP",
  description: "Antes de comprar um imóvel, entenda o lugar.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body style={{ margin: 0, fontFamily: 'ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji"' }}>
        {children}
      </body>
    </html>
  );
}
