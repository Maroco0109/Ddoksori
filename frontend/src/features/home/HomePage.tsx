import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/shared/config/routes';
import { MessageCircle, FileText, MessageSquare } from 'lucide-react';
import { useChatStore } from '@/features/chat/chat.store';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import icon1 from '@/shared/assets/icons/icon-1.png';
import icon2 from '@/shared/assets/icons/icon-2.png';
import icon3 from '@/shared/assets/icons/icon-3.png';

gsap.registerPlugin(ScrollTrigger);

export default function HomePage() {
  const section1Ref = useRef<HTMLDivElement | null>(null);
  const section2Ref = useRef<HTMLDivElement | null>(null);
  const section3Ref = useRef<HTMLDivElement | null>(null);
  const section4Ref = useRef<HTMLDivElement | null>(null);
  const icon1Ref = useRef<HTMLImageElement | null>(null);
  const icon2Ref = useRef<HTMLImageElement | null>(null);
  const icon3Ref = useRef<HTMLImageElement | null>(null);
  const navigate = useNavigate();
  const startNewChat = useChatStore((state) => state.startNewChat);

  useEffect(() => {
    // Lenis 스무스 스크롤 초기화
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
    });

    function raf(time) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);

    // GSAP ScrollTrigger와 Lenis 연동
    lenis.on('scroll', ScrollTrigger.update);

    gsap.ticker.add((time) => {
      lenis.raf(time * 1000);
    });

    gsap.ticker.lagSmoothing(0);

    // 스토리텔링 애니메이션 - 각 섹션별로 설정
    if (section1Ref.current && section2Ref.current && section3Ref.current && icon1Ref.current && icon2Ref.current && icon3Ref.current) {
      // 1단계: icon-1 (등을 돌린 상태) - 스크롤 시 페이드아웃
      gsap.fromTo(
        icon1Ref.current,
        { opacity: 1, scale: 1 },
        {
          opacity: 0,
          scale: 0.8,
          scrollTrigger: {
            trigger: section1Ref.current,
            start: 'top top',
            end: 'bottom top',
            scrub: 1,
          },
        }
      );

      // 2단계: icon-2 (마주보는 상태) - 등장과 퇴장
      const tl2 = gsap.timeline({
        scrollTrigger: {
          trigger: section2Ref.current,
          start: 'top center',
          end: 'bottom top',
          scrub: 1,
        },
      });

      tl2.fromTo(
        icon2Ref.current,
        { opacity: 0, scale: 0.8 },
        { opacity: 1, scale: 1, duration: 0.3 }
      ).to(icon2Ref.current, {
        opacity: 0,
        scale: 0.8,
        duration: 0.7,
      });

      // 3단계: icon-3 (악수하는 상태) - 등장과 유지
      const tl3 = gsap.timeline({
        scrollTrigger: {
          trigger: section3Ref.current,
          start: 'top center',
          end: 'bottom top',
          scrub: 1,
        },
      });

      tl3.fromTo(
        icon3Ref.current,
        { opacity: 0, scale: 0.8 },
        { opacity: 1, scale: 1, duration: 0.3 }
      ).to(icon3Ref.current, {
        opacity: 0,
        scale: 0.8,
        duration: 0.7,
      });
    }

    return () => {
      lenis.destroy();
      ScrollTrigger.getAll().forEach(trigger => trigger.kill());
    };
  }, []);

  return (
    <div className="main-page snap-y snap-mandatory">
      {/* 1페이지: 등을 돌린 상태 */}
      <div
        ref={section1Ref}
        className="relative h-screen flex items-center justify-center bg-gradient-to-br from-lavender/15 to-mint-green/10 snap-start"
      >
        <img
          ref={icon1Ref}
          src={icon1}
          alt="Step 1: 등을 돌린 상태"
          className="w-full max-w-md md:max-w-2xl h-auto object-contain"
        />
      </div>

      {/* 2페이지: 마주보는 상태 */}
      <div
        ref={section2Ref}
        className="relative h-screen flex items-center justify-center bg-gradient-to-br from-mint-green/15 to-lavender/10 snap-start"
      >
        <img
          ref={icon2Ref}
          src={icon2}
          alt="Step 2: 마주보는 상태"
          className="w-full max-w-md md:max-w-2xl h-auto object-contain"
        />
      </div>

      {/* 3페이지: 악수하는 상태 */}
      <div
        ref={section3Ref}
        className="relative h-screen flex items-center justify-center bg-gradient-to-br from-lavender/15 to-mint-green/10 snap-start"
      >
        <img
          ref={icon3Ref}
          src={icon3}
          alt="Step 3: 악수하는 상태"
          className="w-full max-w-md md:max-w-2xl h-auto object-contain"
        />
      </div>

      {/* 4페이지: 텍스트 콘텐츠 */}
      <div
        ref={section4Ref}
        className="relative min-h-screen flex items-center justify-center bg-gradient-to-br from-mint-green/15 to-lavender/10 pt-12 md:pt-16 pb-6 md:pb-8 snap-start"
      >
        <div className="text-center px-4 sm:px-6 md:px-8">
          <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold leading-tight mb-8 md:mb-10 text-dark-navy">
            <span className="text-deep-teal">똑</span>똑한 <span className="text-deep-teal">소</span>비자의 권<span className="text-deep-teal">리</span>,<br />
            <span className="text-deep-teal">똑소리</span>가 지켜드립니다
          </h1>
          <button
            className="inline-flex items-center gap-2 md:gap-3 bg-deep-teal text-white px-6 sm:px-8 md:px-12 py-3 sm:py-4 md:py-5 rounded-full text-sm sm:text-base md:text-lg font-semibold hover:bg-mint-green transform hover:-translate-y-1 transition-all shadow-lg shadow-deep-teal/40 hover:shadow-mint-green/50"
            onClick={() => {
              // 먼저 스크롤을 최상단으로 이동
              window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
              document.documentElement.scrollTop = 0;
              document.body.scrollTop = 0;

              startNewChat();
              navigate(ROUTES.CHAT);
            }}
          >
            <MessageCircle size={18} className="sm:w-5 sm:h-5" />
            무료 상담 시작하기
          </button>
        </div>
      </div>

      {/* Features Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6 md:gap-8 mb-8 md:mb-16">
        <div className="bg-white p-6 sm:p-8 md:p-10 rounded-2xl shadow-lg hover:shadow-2xl hover:-translate-y-2 transition-all">
          <div className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 bg-deep-teal rounded-2xl flex items-center justify-center mb-4 md:mb-6">
            <MessageCircle size={24} className="text-white sm:w-7 sm:h-7 md:w-8 md:h-8" />
          </div>
          <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-3 md:mb-4 text-dark-navy">AI 챗봇</h3>
          <p className="text-sm sm:text-base text-gray-purple leading-relaxed">
            언제나 실시간으로 응답합니다
          </p>
        </div>

        <div className="bg-white p-6 sm:p-8 md:p-10 rounded-2xl shadow-lg hover:shadow-2xl hover:-translate-y-2 transition-all">
          <div className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 bg-lavender rounded-2xl flex items-center justify-center mb-4 md:mb-6">
            <FileText size={24} className="text-white sm:w-7 sm:h-7 md:w-8 md:h-8" />
          </div>
          <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-3 md:mb-4 text-dark-navy">실제 공공 데이터</h3>
          <p className="text-sm sm:text-base text-gray-purple leading-relaxed">
            공공기관의 실제 분쟁조정 사례를 기반으로 안내합니다
          </p>
        </div>

        <div className="bg-white p-6 sm:p-8 md:p-10 rounded-2xl shadow-lg hover:shadow-2xl hover:-translate-y-2 transition-all">
          <div className="w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 bg-mint-green rounded-2xl flex items-center justify-center mb-4 md:mb-6">
            <MessageSquare size={24} className="text-white sm:w-7 sm:h-7 md:w-8 md:h-8" />
          </div>
          <h3 className="text-lg sm:text-xl md:text-2xl font-bold mb-3 md:mb-4 text-dark-navy">커뮤니티를 통한 경험 공유</h3>
          <p className="text-sm sm:text-base text-gray-purple leading-relaxed">
            실제 소비자들의 분쟁 해결 경험을 공유하고 배웁니다
          </p>
        </div>
      </div>

      {/* Stats Section */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 md:gap-8 bg-dark-navy p-6 sm:p-8 md:p-12 rounded-2xl text-white">
        <div className="text-center">
          <div className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-mint-green mb-1 md:mb-2">무료</div>
          <div className="text-xs sm:text-sm md:text-base opacity-80">AI 상담 비용</div>
        </div>
        <div className="text-center">
          <div className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-mint-green mb-1 md:mb-2">즉시</div>
          <div className="text-xs sm:text-sm md:text-base opacity-80">24/7 실시간 상담</div>
        </div>
        <div className="text-center">
          <div className="text-3xl sm:text-4xl md:text-5xl font-extrabold text-mint-green mb-1 md:mb-2">유일</div>
          <div className="text-xs sm:text-sm md:text-base opacity-80">소비자 커뮤니티</div>
        </div>
      </div>
    </div>
  );
}
