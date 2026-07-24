"""
FIXED Enhanced Chat PDF Export - Handles Long Messages
Generates professional PDFs that work with any message length
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, 
    Table, TableStyle, KeepTogether, HRFlowable, Frame
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.colors import HexColor
from datetime import datetime
from io import BytesIO
from typing import List, Dict, Any
import re
import logging

logger = logging.getLogger(__name__)


class ChatPDFGenerator:
    """Generate beautiful, professional PDF exports that handle any message length"""
    
    # Color scheme
    PRIMARY_COLOR = HexColor('#2563eb')
    SECONDARY_COLOR = HexColor('#3b82f6')
    USER_BG = HexColor('#eff6ff')
    ASSISTANT_BG = HexColor('#f9fafb')
    ACCENT_COLOR = HexColor('#10b981')
    TEXT_COLOR = HexColor('#1f2937')
    MUTED_COLOR = HexColor('#6b7280')
    BORDER_COLOR = HexColor('#e5e7eb')
    
    def __init__(self, page_size=letter):
        """Initialize PDF generator"""
        self.page_size = page_size
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
    
    def _create_custom_styles(self):
        """Create beautiful custom paragraph styles"""
        
        # Title style
        self.styles.add(ParagraphStyle(
            name='ChatTitle',
            parent=self.styles['Title'],
            fontSize=26,
            textColor=self.PRIMARY_COLOR,
            spaceAfter=12,
            spaceBefore=0,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Metadata style
        self.styles.add(ParagraphStyle(
            name='Metadata',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=self.MUTED_COLOR,
            spaceAfter=25,
            alignment=TA_CENTER
        ))
        
        # Message number style
        self.styles.add(ParagraphStyle(
            name='MessageNumber',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=self.MUTED_COLOR,
            spaceAfter=8,
            fontName='Helvetica-Bold'
        ))
        
        # User label style
        self.styles.add(ParagraphStyle(
            name='UserLabel',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=self.PRIMARY_COLOR,
            spaceAfter=4,
            fontName='Helvetica-Bold'
        ))
        
        # User message style - NO TABLE, just styled paragraph
        self.styles.add(ParagraphStyle(
            name='UserMessage',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=self.TEXT_COLOR,
            leftIndent=20,
            rightIndent=20,
            spaceAfter=12,
            spaceBefore=4,
            leading=15,
            borderWidth=1,
            borderColor=self.PRIMARY_COLOR,
            borderPadding=10,
            backColor=self.USER_BG
        ))
        
        # Assistant label style
        self.styles.add(ParagraphStyle(
            name='AssistantLabel',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=self.SECONDARY_COLOR,
            spaceAfter=4,
            fontName='Helvetica-Bold'
        ))
        
        # Assistant message style - NO TABLE, allows page breaks
        self.styles.add(ParagraphStyle(
            name='AssistantMessage',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=self.TEXT_COLOR,
            leftIndent=20,
            rightIndent=20,
            spaceAfter=15,
            spaceBefore=4,
            leading=15,
            alignment=TA_JUSTIFY,
            borderWidth=1,
            borderColor=self.BORDER_COLOR,
            borderPadding=10,
            backColor=self.ASSISTANT_BG
        ))
        
        # Sources style
        self.styles.add(ParagraphStyle(
            name='Sources',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=self.ACCENT_COLOR,
            leftIndent=20,
            spaceAfter=10,
            fontName='Helvetica-Bold'
        ))
        
        # Table cell style
        self.styles.add(ParagraphStyle(
            name='TableCell',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=self.TEXT_COLOR,
            leading=14
        ))
    
    @staticmethod
    def _convert_markdown_to_reportlab(text: str) -> str:
        """Convert markdown to ReportLab-compatible HTML"""
        if not text:
            return ""
        
        # Escape XML characters
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        
        # Convert markdown formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)
        text = re.sub(r'`(.*?)`', r'<font face="Courier" color="#d97706">\1</font>', text)
        
        # Headers
        text = re.sub(r'^### (.*?)$', r'<b><font size="12" color="#2563eb">\1</font></b>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.*?)$', r'<b><font size="13" color="#2563eb">\1</font></b>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.*?)$', r'<b><font size="14" color="#2563eb">\1</font></b>', text, flags=re.MULTILINE)
        
        # Bullet points
        text = re.sub(r'^[\-\*] (.*?)$', r'• \1', text, flags=re.MULTILINE)
        
        # Numbered lists
        text = re.sub(r'^\d+\. (.*?)$', r'<seq/>. \1', text, flags=re.MULTILINE)
        
        # Line breaks
        text = text.replace('\n', '<br/>')
        
        return text
    
    def _parse_markdown_table(self, text: str) -> tuple:
        """Extract and parse markdown tables"""
        tables = []
        table_pattern = r'\|(.+)\|[\r\n]+\|[-:\s|]+\|[\r\n]+((?:\|.+\|[\r\n]*)+)'
        
        def extract_table(match):
            header_row = match.group(1)
            body_rows = match.group(2)
            
            headers = [cell.strip() for cell in header_row.split('|') if cell.strip()]
            rows = []
            for row in body_rows.strip().split('\n'):
                if '|' in row:
                    cells = [cell.strip() for cell in row.split('|') if cell.strip()]
                    if cells:
                        rows.append(cells)
            
            if headers and rows:
                tables.append({'headers': headers, 'rows': rows})
            return '\n[TABLE_' + str(len(tables) - 1) + ']\n'
        
        text_without_tables = re.sub(table_pattern, extract_table, text)
        return text_without_tables, tables
    
    def _create_table(self, table_data: dict) -> Table:
        """Create a beautifully formatted table"""
        headers = table_data['headers']
        rows = table_data['rows']
        
        # Wrap cells in Paragraphs for better text wrapping
        wrapped_headers = [Paragraph(f"<b>{h}</b>", self.styles['TableCell']) for h in headers]
        wrapped_rows = [[Paragraph(str(cell), self.styles['TableCell']) for cell in row] for row in rows]
        
        data = [wrapped_headers] + wrapped_rows
        
        # Dynamic column widths
        page_width = self.page_size[0] - 1.5*inch
        col_count = len(headers)
        col_widths = [page_width / col_count] * col_count
        
        table = Table(data, colWidths=col_widths, repeatRows=1)
        
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), self.PRIMARY_COLOR),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            
            # Body
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), self.TEXT_COLOR),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            
            # Borders
            ('GRID', (0, 0), (-1, -1), 0.5, self.BORDER_COLOR),
            ('BOX', (0, 0), (-1, -1), 1.5, self.PRIMARY_COLOR),
            
            # Alternating rows
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HexColor('#f9fafb')]),
        ]))
        
        return table
    
    @staticmethod
    def _format_timestamp(timestamp_str: str) -> str:
        """Format timestamp"""
        try:
            dt = datetime.fromisoformat(str(timestamp_str).replace('Z', '+00:00'))
            return dt.strftime('%B %d, %Y at %I:%M %p')
        except:
            return str(timestamp_str)
    
    def generate_pdf(
        self,
        chat_title: str,
        messages: List[Dict[str, Any]],
        metadata: Dict[str, Any] = None
    ) -> BytesIO:
        """
        Generate PDF - FIXED to handle long messages
        """
        try:
            buffer = BytesIO()
            
            doc = SimpleDocTemplate(
                buffer,
                pagesize=self.page_size,
                rightMargin=0.75*inch,
                leftMargin=0.75*inch,
                topMargin=0.75*inch,
                bottomMargin=0.75*inch
            )
            
            elements = []
            
            # Title
            elements.append(Paragraph(self._convert_markdown_to_reportlab(chat_title), self.styles['ChatTitle']))
            elements.append(Spacer(1, 0.15*inch))
            
            # Metadata
            if metadata:
                metadata_text = f"Exported on {datetime.now().strftime('%B %d, %Y')}"
                if metadata.get('message_count'):
                    metadata_text += f" • {metadata['message_count']} messages"
                elements.append(Paragraph(metadata_text, self.styles['Metadata']))
            
            # Separator
            elements.append(HRFlowable(
                width="100%",
                thickness=2,
                color=self.BORDER_COLOR,
                spaceBefore=5,
                spaceAfter=15
            ))
            
            # Messages
            for idx, message in enumerate(messages, 1):
                # Message number
                created_at = message.get('created_at')
                timestamp_str = self._format_timestamp(created_at) if created_at else ""
                elements.append(
                    Paragraph(
                        f"<b>Message {idx}</b> • {timestamp_str}",
                        self.styles['MessageNumber']
                    )
                )
                
                # USER QUESTION - Using Paragraph with borders (allows page breaks)
                elements.append(Paragraph("💬 You:", self.styles['UserLabel']))
                query_text = self._convert_markdown_to_reportlab(message.get('query_text', ''))
                elements.append(Paragraph(query_text, self.styles['UserMessage']))
                
                elements.append(Spacer(1, 0.1*inch))
                
                # ASSISTANT RESPONSE - Using Paragraph (allows page breaks)
                elements.append(Paragraph("🤖 Assistant:", self.styles['AssistantLabel']))
                
                response_text = message.get('response_text', '')
                
                # Parse tables
                response_text, tables = self._parse_markdown_table(response_text)
                
                # Convert markdown
                response_text = self._convert_markdown_to_reportlab(response_text)
                
                # Add response as Paragraph (can split across pages!)
                elements.append(Paragraph(response_text, self.styles['AssistantMessage']))
                
                # Add tables separately
                if tables:
                    elements.append(Spacer(1, 0.1*inch))
                    for table_data in tables:
                        elements.append(self._create_table(table_data))
                        elements.append(Spacer(1, 0.1*inch))
                
                # Sources
                sources = message.get('sources_used')
                if sources and isinstance(sources, list) and len(sources) > 0:
                    source_names = []
                    for source in sources[:5]:
                        if isinstance(source, dict):
                            source_names.append(source.get('source_file', 'Unknown'))
                        else:
                            source_names.append(str(source))
                    
                    sources_text = "📎 <b>Sources:</b> " + ", ".join(source_names)
                    if len(sources) > 5:
                        sources_text += f" and {len(sources) - 5} more"
                    
                    elements.append(Paragraph(sources_text, self.styles['Sources']))
                
                # Separator between messages
                if idx < len(messages):
                    elements.append(Spacer(1, 0.15*inch))
                    elements.append(HRFlowable(
                        width="100%",
                        thickness=1,
                        color=self.BORDER_COLOR,
                        spaceBefore=5,
                        spaceAfter=15
                    ))
            
            # Build PDF
            doc.build(elements)
            buffer.seek(0)
            
            logger.info(f"✅ Generated PDF with {len(messages)} messages")
            
            return buffer
            
        except Exception as e:
            logger.error(f"❌ Error generating PDF: {str(e)}", exc_info=True)
            raise
    
    def generate_pdf_from_shared_chat(self, shared_chat_data: Dict[str, Any]) -> BytesIO:
        """Generate PDF from shared chat data"""
        metadata = {
            'message_count': shared_chat_data.get('message_count'),
            'created_at': shared_chat_data.get('created_at')
        }
        
        return self.generate_pdf(
            chat_title=shared_chat_data.get('share_title', 'Chat Export'),
            messages=shared_chat_data.get('messages', []),
            metadata=metadata
        )


# Convenience function
def generate_chat_pdf(
    chat_title: str,
    messages: List[Dict[str, Any]],
    metadata: Dict[str, Any] = None,
    page_size=letter
) -> BytesIO:
    """Generate PDF with fixed long message handling"""
    generator = ChatPDFGenerator(page_size=page_size)
    return generator.generate_pdf(chat_title, messages, metadata)