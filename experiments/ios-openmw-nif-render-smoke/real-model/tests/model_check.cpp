#include "StaticModel.hpp"
#include <iostream>
#include <osg/ComputeBoundsVisitor>
#include <osg/Texture2D>
int main(int argc,char** argv){try{if(argc!=3&&argc!=4)throw std::runtime_error("Usage: model-check private-directory STAT-id [fixture]");
 auto model=G1D::load(argv[1],argv[2]);osg::ComputeBoundsVisitor visitor;model.scene->accept(visitor);auto bounds=visitor.getBoundingBox();
 if(!bounds.valid())throw std::runtime_error("Owned scene has invalid bounds after parser/VFS release");
 if(argc==4&&(bounds.xMin()!=1||bounds.xMax()!=2||bounds.yMin()!=2||bounds.yMax()!=3||bounds.zMin()!=3||bounds.zMax()!=3))throw std::runtime_error("Hierarchy transform/ownership mismatch");
 if(argc==4){auto* root=model.scene->getChild(0)->asGroup();auto* child=root->getChild(0)->asGroup();auto* shape=child->getChild(0)->asGroup();auto* geode=shape->getChild(0);
 auto* tex=dynamic_cast<osg::Texture2D*>(geode->getStateSet()->getTextureAttribute(0,osg::StateAttribute::TEXTURE));
 if(!tex||!tex->getImage()||tex->getImage()->s()!=4||tex->getImage()->data()[0]!=255||tex->getImage()->data()[3]!=255)throw std::runtime_error("DDS decode/owned image mismatch");}
 std::cout<<"{\"status\":\"PASS\",\"vertices\":"<<model.vertices<<",\"triangles\":"<<model.triangles<<",\"shapes\":"<<model.shapes<<"}\n";return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
