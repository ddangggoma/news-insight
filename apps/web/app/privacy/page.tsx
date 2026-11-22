import type { Metadata } from "next";

export const metadata: Metadata = { title: "Privacy Policy · 개인정보처리방침" };
// the contact address comes from the environment at request time, never from the repository
export const dynamic = "force-dynamic";

const UPDATED = "2026-11-19";

function Section({ id, title, children }: { id?: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="space-y-2">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-muted-foreground">{children}</div>
    </section>
  );
}

// Public page (proxy.ts leaves /privacy alone): the Threads API app review asks for a privacy
// policy and data deletion instructions URL that anyone can open (docs/runbooks/threads-api.md).
export default function PrivacyPage() {
  const contact = process.env.PRIVACY_CONTACT_EMAIL?.trim();
  return (
    <main className="mx-auto max-w-2xl space-y-8 px-4 py-10">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Privacy Policy · 개인정보처리방침</h1>
        <p className="text-sm text-muted-foreground">Last updated {UPDATED}</p>
      </header>

      <Section title="What this service is">
        <p>
          Daily IT Intelligence is a private technology news monitoring service run by one person for
          their own research. It reads public news, research and community posts about
          technology and summarizes the trends. It has no advertising and sells no data.
        </p>
        <p>
          Daily IT Intelligence는 운영자 개인의 기술 동향 파악을 위한 비공개 서비스입니다. 공개된 뉴스·논문·커뮤니티
          글을 읽어 기술 흐름을 요약하며, 광고나 데이터 판매는 없습니다.
        </p>
      </Section>

      <Section title="Data we use from Threads">
        <p>
          Through the Threads API we read public posts that match technology keywords (for
          example &ldquo;humanoid robot&rdquo; or &ldquo;AI chip&rdquo;) and public posts of a
          few technology publishers. For each post we keep its link, author username, time,
          the first 500 characters of its text and its public reaction counts.
        </p>
        <p>
          We do not read private profiles, direct messages, followers or any data of people who
          log in to this service. We never publish, sell or share Threads data with others, and
          we do not use it to train AI models.
        </p>
        <p>
          Threads API로는 기술 키워드와 일치하는 공개 글과 일부 IT 매체의 공개 글만 읽습니다. 글 링크, 작성자
          아이디, 작성 시각, 본문 앞 500자, 공개 반응 수만 저장하며, 비공개 정보·메시지·팔로워 정보는 읽지
          않습니다. 수집한 데이터를 공개·판매·제공하거나 AI 학습에 쓰지 않습니다.
        </p>
      </Section>

      <Section title="How long we keep it">
        <p>
          Posts are kept for trend analysis and are deleted on request (see below).
        </p>
        <p>수집한 글은 기술 동향 분석에 쓰며, 요청이 있으면 삭제합니다.</p>
      </Section>

      <Section id="data-deletion" title="Data deletion · 데이터 삭제 요청">
        <p>
          To have your Threads posts removed from this service, send the link of your Threads
          profile or post {contact ? <>to <a className="underline" href={`mailto:${contact}`}>{contact}</a></> : "to the operator"}.
          We delete every stored copy within 30 days and reply to confirm.
        </p>
        <p>
          본인 Threads 글의 삭제를 원하면 프로필 또는 글 링크를 보내 주세요. 30일 안에 저장된 사본을 모두 지우고
          결과를 알려드립니다.
        </p>
      </Section>

      <Section title="Contact">
        <p>{contact ? <a className="underline" href={`mailto:${contact}`}>{contact}</a> : "Contact the operator of this site."}</p>
      </Section>
    </main>
  );
}
