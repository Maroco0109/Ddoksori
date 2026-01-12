import { useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowLeft, Send } from 'lucide-react';
import { CATEGORY_LABELS, POST_CATEGORIES } from '@/shared/config/categories';
import type { BoardPostForm } from '../board.types';

interface WritePostProps {
  onBack: () => void;
  onSubmit: (data: BoardPostForm) => void;
}

type WritePostFormState = {
  category: BoardPostForm['category'] | '';
  title: string;
  content: string;
};

export default function WritePost({ onBack, onSubmit }: WritePostProps) {
  const [formData, setFormData] = useState<WritePostFormState>({
    category: '',
    title: '',
    content: ''
  });

  const categories = [
    { id: 'case-sharing', name: '분쟁해결사례 공유' },
    { id: 'qna', name: '무엇이든 물어보세요' },
    { id: 'tips', name: '소비자 꿀팁/노하우' }
  ];

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!formData.category || !formData.title.trim() || !formData.content.trim()) {
      alert('모든 필드를 입력해주세요.');
      return;
    }
    onSubmit({
      category: formData.category as BoardPostForm['category'],
      title: formData.title,
      content: formData.content,
    });
  };

  return (
    <div className="write-post-page">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6 md:mb-8">
        <button
          onClick={onBack}
          className="p-2 hover:bg-gray-100 rounded-full transition-colors"
        >
          <ArrowLeft size={24} className="text-dark-navy" />
        </button>
        <h1 className="text-2xl sm:text-3xl md:text-4xl font-extrabold text-dark-navy">글쓰기</h1>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-md p-6 md:p-8">
        {/* Category Selection */}
        <div className="mb-6">
          <label className="block text-sm font-semibold text-gray-700 mb-3">
            카테고리 <span className="text-red-500">*</span>
          </label>
          <div className="flex flex-wrap gap-3">
            {categories.map(cat => (
              <button
                key={cat.id}
                type="button"
                className={`px-5 py-2.5 rounded-full text-sm font-medium transition-all ${
                  formData.category === cat.id
                    ? 'bg-deep-teal text-white'
                    : 'bg-white border-2 border-gray-200 text-gray-700 hover:border-lavender'
                }`}
                onClick={() => setFormData({ ...formData, category: cat.id })}
              >
                {cat.name}
              </button>
            ))}
          </div>
        </div>

        {/* Title Input */}
        <div className="mb-6">
          <label htmlFor="title" className="block text-sm font-semibold text-gray-700 mb-3">
            제목 <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            id="title"
            value={formData.title}
            onChange={(e) => setFormData({ ...formData, title: e.target.value })}
            placeholder="제목을 입력하세요"
            className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg outline-none focus:border-deep-teal transition-colors text-sm md:text-base"
            maxLength={100}
          />
          <p className="text-xs text-gray-500 mt-2 text-right">{formData.title.length}/100</p>
        </div>

        {/* Content Input */}
        <div className="mb-6">
          <label htmlFor="content" className="block text-sm font-semibold text-gray-700 mb-3">
            내용 <span className="text-red-500">*</span>
          </label>
          <textarea
            id="content"
            value={formData.content}
            onChange={(e) => setFormData({ ...formData, content: e.target.value })}
            placeholder="내용을 입력하세요"
            rows={12}
            className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg outline-none focus:border-deep-teal transition-colors text-sm md:text-base resize-none"
            maxLength={5000}
          />
          <p className="text-xs text-gray-500 mt-2 text-right">{formData.content.length}/5000</p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row gap-3 justify-end">
          <button
            type="button"
            onClick={onBack}
            className="px-8 py-3 border-2 border-gray-300 text-gray-700 rounded-full font-semibold hover:bg-gray-50 transition-all"
          >
            취소
          </button>
          <button
            type="submit"
            className="px-8 py-3 bg-deep-teal text-white rounded-full font-semibold hover:bg-mint-green transition-all flex items-center justify-center gap-2"
          >
            <Send size={18} />
            등록하기
          </button>
        </div>
      </form>
    </div>
  );
}
